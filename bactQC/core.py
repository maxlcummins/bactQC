# bactQC/core.py

import os
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import json
import logging
import re
from functools import lru_cache
from .version import __version__
from collections import defaultdict
from typing import Optional
from threading import Lock
from glob import glob
from datetime import datetime

# For faster XML parsing, use lxml if available
try:
    from lxml import etree
    XML_PARSER = 'lxml'
except ImportError:
    XML_PARSER = 'etree'

# Configure logging at the module level
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Genome:
    def __init__(self, sample_name=None, input_dir='bactopia'):
        self.input_dir = input_dir

        if sample_name is None:
            self.sample_names = [
                d for d in os.listdir(input_dir)
                if os.path.isdir(os.path.join(input_dir, d)) and d != 'bactopia-runs'
            ]
        else:
            self.sample_names = [sample_name]

        # Initialize qc_data, qc_results, qc_requirements as dictionaries
        self.qc_data = {}
        self.qc_results = {}
        self.qc_requirements = {}

        # Initialize a cache for taxid to genome size data
        self.taxid_cache = {}
        self.cache_lock = Lock()  # To make cache thread-safe if parallelization is used

        # Initialize a persistent HTTP session
        self.session = requests.Session()

        # Initialize CheckM data cache
        self.checkm_data = None  # Will hold the DataFrame after loading

        logger.info(f"bactQC version {__version__} initialized.")

    def run(self, min_primary_abundance=0.60, min_completeness=80,
            max_contamination=10, maximum_contigs=500, minimum_n50=15000,
            min_q30_bases=0.85, min_coverage=30):
        """
        Run all quality control checks for the sample(s).
        """
        # Preload CheckM data once before processing samples
        self._load_checkm_data()

        for sample_name in self.sample_names:
            # Initialize data structures for the sample
            self.qc_data[sample_name] = {'sample': sample_name}
            self.qc_results[sample_name] = {}
            self.qc_requirements[sample_name] = {}
            logger.info(f"Processing sample {sample_name}")
            try:
                logger.info("Getting expected genome size")
                self.get_expected_genome_size(sample_name)
                logger.info("Determining assembly size")
                self.get_assembly_size(sample_name)
                logger.info("Analysing Bracken data")
                self.check_bracken(sample_name, min_primary_abundance)
                expected_genus = self.qc_data[sample_name]['genome_size']['organism_name'].split()[0]
                logger.info("Analysing MLST data")
                self.check_mlst(sample_name, expected_genus)
                logger.info("Analysing CheckM data")
                self.check_checkm(sample_name, min_completeness, max_contamination)
                logger.info("Analysing Assembly Scan data")
                self.check_assembly_scan(sample_name, maximum_contigs, minimum_n50)
                logger.info("Analysing FastP data")
                self.check_fastp(sample_name, min_q30_bases, min_coverage)
                logger.info("Overall QC")
                self.overall_qc(sample_name)
            except Exception as e:
                logger.error(f"Error processing sample {sample_name}: {e}")
                self.qc_results[sample_name]['overall'] = False

    def _load_checkm_data(self):
        """
        Loads and caches the most recent CheckM data from 'checkm.tsv' files.
        This method is called once before processing samples to avoid redundant I/O operations.
        """
        if self.checkm_data is not None:
            logger.info("CheckM data already loaded. Using cached data.")
            return  # Already loaded

        logger.info(f"Searching for CheckM files in {os.path.join(self.input_dir, 'bactopia-runs')}")

        # Use glob to find all 'checkm.tsv' files recursively
        checkm_pattern = os.path.join(self.input_dir, 'bactopia-runs', '**', 'checkm.tsv')
        checkm_files = glob(checkm_pattern, recursive=True)

        if not checkm_files:
            raise ValueError(f"CheckM data not found in any 'checkm.tsv' files within '{os.path.join(self.input_dir, 'bactopia-runs')}'")

        # Determine the most recent checkm.tsv file based on directory timestamp
        # Assumption: The grandparent directory name contains a timestamp in a sortable format
        def extract_timestamp(file_path):
            """
            Extracts a timestamp from the grandparent directory's name.
            Assumes the directory name is a timestamp in ISO format or similar.
            """
            try:
                grandparent_dir = os.path.basename(os.path.dirname(os.path.dirname(file_path)))
                # Attempt to parse the directory name as a date
                return datetime.strptime(grandparent_dir, '%Y%m%d%H%M%S')
            except ValueError:
                # If parsing fails, use the directory name as is for sorting
                return grandparent_dir

        # Sort the checkm_files based on extracted timestamps
        checkm_files_sorted = sorted(checkm_files, key=extract_timestamp)

        # Select the most recent checkm.tsv file
        file_path = checkm_files_sorted[-1]
        logger.info(f"Loading CheckM data from the most recent file: {file_path}")

        # Read the CheckM TSV file
        try:
            checkm_df = pd.read_csv(file_path, sep='\t')
        except Exception as e:
            logger.error(f"Error reading CheckM file '{file_path}': {e}")
            raise

        if 'Bin Id' not in checkm_df.columns:
            raise ValueError(f"'Bin Id' column not found in CheckM file '{file_path}'")

        # Rename 'Bin Id' to 'sample' for consistency
        checkm_df.rename(columns={'Bin Id': 'sample'}, inplace=True)

        # Set 'sample' as the index for faster lookups
        checkm_df.set_index('sample', inplace=True)

        self.checkm_data = checkm_df
        logger.info("CheckM data loaded and cached successfully.")

    def check_checkm(self, sample_name, min_completeness=80, max_contamination=10):
        """
        Checks CheckM results for a given sample and evaluates quality metrics.

        Updates self.qc_data[sample_name]['checkm'] with the results.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        if self.checkm_data is None:
            # Load CheckM data if not already loaded
            self._load_checkm_data()

        # Check if the sample exists in the CheckM data
        if sample_name not in self.checkm_data.index:
            raise ValueError(f"Sample '{sample_name}' not found in the loaded CheckM data.")

        # Extract the CheckM results for the sample
        checkm_row = self.checkm_data.loc[sample_name]

        # If there are multiple entries for the sample, handle accordingly
        if isinstance(checkm_row, pd.DataFrame):
            # If multiple rows exist for the sample, select the first one or handle as needed
            checkm_row = checkm_row.iloc[0]

        # Convert the row to a dictionary
        checkm_result = checkm_row.to_dict()

        # Add requirement thresholds
        checkm_result['completeness_requirement'] = min_completeness
        checkm_result['contamination_requirement'] = max_contamination

        # Evaluate quality metrics
        # Ensure that 'Completeness' and 'Contamination' columns exist
        if 'Completeness' not in checkm_result or 'Contamination' not in checkm_result:
            raise ValueError(f"Missing 'Completeness' or 'Contamination' in CheckM data for sample '{sample_name}'.")

        # Compute pass/fail flags
        checkm_result['passed_completeness'] = checkm_result['Completeness'] > min_completeness
        checkm_result['passed_contamination'] = checkm_result['Contamination'] < max_contamination
        checkm_result['passed_checkm_QC'] = checkm_result['passed_completeness'] and checkm_result['passed_contamination']

        # Update qc_data, qc_results, qc_requirements
        self.qc_data[sample_name]['checkm'] = checkm_result
        self.qc_results[sample_name]['checkm'] = checkm_result['passed_checkm_QC']
        self.qc_requirements[sample_name]['checkm'] = {
            'max_contamination': max_contamination,
            'min_completeness': min_completeness
        }

        logger.info(f"CheckM processing complete for sample '{sample_name}'.")

    def get_expected_genome_size(self, sample_name):
        """
        Retrieve expected genome size information from the NCBI API based on Bracken results.
        Optimized with caching and persistent HTTP session.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        # Determine taxid for the sample
        bracken_path = os.path.join(
            self.input_dir, sample_name, 'tools', 'bracken',
            f"{sample_name}.bracken.adjusted.abundances.txt"
        )
        if not os.path.isfile(bracken_path):
            raise FileNotFoundError(f"Bracken abundance file not found at {bracken_path}")

        # Read only the necessary column to reduce memory usage
        try:
            bracken_result = pd.read_csv(bracken_path, sep='\t', usecols=['taxonomy_id'])
        except ValueError as e:
            raise ValueError(f"Bracken abundance file at {bracken_path} is missing 'taxonomy_id' column: {e}")

        if bracken_result.empty:
            raise ValueError(f"Bracken abundance file at {bracken_path} is empty.")

        taxid = str(bracken_result.iloc[0]['taxonomy_id'])

        # Check if taxid is already cached
        with self.cache_lock:
            if taxid in self.taxid_cache:
                logger.info(f"Using cached genome size data for taxid {taxid}")
                data = self.taxid_cache[taxid]
            else:
                base_URL = "https://api.ncbi.nlm.nih.gov/genome/v0/expected_genome_size/expected_genome_size?species_taxid="
                url = f"{base_URL}{taxid}"

                # Fetch genome size data using the persistent session
                try:
                    response = self.session.get(url, timeout=10)
                    response.raise_for_status()
                except requests.RequestException as e:
                    logger.error(f"Error fetching genome size data for taxid {taxid}: {e}")
                    raise

                data = {}
                if response.content:
                    try:
                        if XML_PARSER == 'lxml':
                            root = etree.fromstring(response.content)
                        else:
                            root = ET.fromstring(response.content)
                        data = {
                            'organism_name': root.findtext('organism_name'),
                            'species_taxid': root.findtext('species_taxid'),
                            'expected_ungapped_length': int(root.findtext('expected_ungapped_length')),
                            'minimum_ungapped_length': int(root.findtext('minimum_ungapped_length')),
                            'maximum_ungapped_length': int(root.findtext('maximum_ungapped_length'))
                        }
                    except (ET.ParseError, etree.XMLSyntaxError) as e:
                        logger.error(f"Error parsing XML for taxid {taxid}: {e}")
                        raise
                else:
                    logger.warning(f"No content returned for taxid {taxid}")
                    raise ValueError(f"No content returned for taxid {taxid}")

                if data and data.get('organism_name'):
                    # Cache the result
                    self.taxid_cache[taxid] = data
                else:
                    raise ValueError(f"Failed to retrieve genome size for taxid {taxid}. 'organism_name' is missing.")

        self.qc_data[sample_name]['genome_size'] = data

    def get_assembly_size(self, sample_name):
        """
        Retrieves the total contig length in base-pairs for a given sample from the assembler results.

        Updates self.qc_data[sample_name]['assembly_size'] with the results.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        # Construct the file path to the assembler results
        file_path = os.path.join(self.input_dir, sample_name, 'main', 'assembler', f"{sample_name}.tsv")

        # Check if the file exists
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Assembly results file not found for sample '{sample_name}' at '{file_path}'")

        # Read the assembler results file
        assembly_scan_df = pd.read_csv(file_path, sep='\t')

        # Ensure the DataFrame has exactly one row
        if assembly_scan_df.shape[0] != 1:
            raise ValueError(f"Sample '{sample_name}': Expected one row in assembly scan data, but got {assembly_scan_df.shape[0]} rows")

        # Extract the total_contig_length from the first (and only) row
        total_length = assembly_scan_df.iloc[0]['total_contig_length']

        self.qc_data[sample_name]['assembly_size'] = {'total_length': total_length}

    def check_bracken(self, sample_name, min_primary_abundance=0.60):
        """
        Check Bracken results for a given sample.

        Updates self.qc_data[sample_name]['bracken'] with the results.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        # Get the file path
        file_path = os.path.join(self.input_dir, sample_name, 'tools', 'bracken', f"{sample_name}.bracken.tsv")

        # Check the path exists
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Bracken data not found at {file_path}")

        # Read the file
        bracken_result = pd.read_csv(file_path, sep='\t')

        # Check that bracken_result has only one row
        if bracken_result.shape[0] != 1:
            raise ValueError(f"Sample {sample_name}: Expected one row for bracken, but got {bracken_result.shape[0]} rows")

        # Add a column with a boolean for whether bracken_primary_species_abundance is greater than min_primary_abundance for first row
        bracken_result['passed_bracken_QC'] = bracken_result['bracken_primary_species_abundance'] > min_primary_abundance

        # Take the first row and convert it to a dictionary after dropping the 'sample' column
        bracken_result = bracken_result.iloc[0].drop('sample').to_dict()

        # Add an entry with the minimum primary abundance
        bracken_result['primary_abundance_requirement'] = min_primary_abundance

        # Check for genus conflict
        has_secondary_species = bracken_result['bracken_secondary_species'] != 'No secondary abundance > 1%'

        primary_genus = bracken_result['bracken_primary_species'].split()[0] if bracken_result['bracken_primary_species'] else ''
        secondary_genus = bracken_result['bracken_secondary_species'].split()[0] if bracken_result['bracken_secondary_species'] else ''
        is_ecoli_or_shigella = {'Escherichia', 'Shigella'} == {primary_genus, secondary_genus}

        if has_secondary_species and is_ecoli_or_shigella:
            bracken_result['genus_conflict'] = primary_genus != secondary_genus
        else:
            bracken_result['genus_conflict'] = False

        self.qc_data[sample_name]['bracken'] = bracken_result

        self.qc_results[sample_name]['bracken'] = bracken_result['passed_bracken_QC']

        self.qc_requirements[sample_name]['bracken'] = {'min_primary_abundance': min_primary_abundance}

    def check_mlst(self, sample_name, expected_genus=None):
        """
        Check MLST results for a given sample.

        If expected_genus is not provided, derive it from genome_size.

        Updates self.qc_data[sample_name]['mlst'] with the results.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        # If expected_genus is not provided, derive it from genome_size
        if expected_genus is None:
            organism_name = self.qc_data[sample_name].get('genome_size', {}).get('organism_name', None)
            if organism_name:
                expected_genus = organism_name.split()[0]
                logger.info(f"Derived expected_genus from genome_size: {expected_genus}")
            else:
                # Attempt to retrieve genome_size if not already done
                try:
                    self.get_expected_genome_size(sample_name)
                    organism_name = self.qc_data[sample_name].get('genome_size', {}).get('organism_name', None)
                    if organism_name:
                        expected_genus = organism_name.split()[0]
                        logger.info(f"Derived expected_genus from genome_size after fetching: {expected_genus}")
                    else:
                        raise ValueError
                except Exception:
                    raise ValueError("Organism name not found in genome_size data to derive expected_genus.")

        # Get the file path
        file_path = os.path.join(self.input_dir, sample_name, 'tools', 'mlst', f"{sample_name}.tsv")

        # Check the path exists
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"MLST data not found at {file_path}")

        # Read the file
        mlst_result = pd.read_csv(file_path, sep='\t', header=None)

        # Check that mlst_result has only one row
        if mlst_result.shape[0] != 1:
            raise ValueError(f"Sample {sample_name}: Expected one row in MLST data, but got {mlst_result.shape[0]} rows")

        # Check if any MLST alleles were detected
        if mlst_result.iloc[0, 1] == '-' and mlst_result.iloc[0, 2] == '-':
            self.qc_data[sample_name]['mlst'] = {
                'scheme': '-', 'ST': '-', 'allele1': '-', 'allele2': '-', 'allele3': '-', 'allele4': '-', 'allele5': '-', 'allele6': '-', 'allele7': '-'
            }
            self.qc_results[sample_name]['mlst'] = False
            self.qc_requirements[sample_name]['mlst'] = {'expected_genus': '-'}
            logger.info(f"MLST processing complete - no MLST scheme alleles detected for {sample_name}")
            return

        # Define the column names
        mlst_result.columns = ['sample', 'scheme', 'ST', 'allele1', 'allele2', 'allele3', 'allele4', 'allele5', 'allele6', 'allele7']

        # Remove file extensions from the sample column
        mlst_result['sample'] = mlst_result['sample'].str.replace(r'\.(fna|fasta|fa)(\.gz)?$', '', regex=True)

        # Download the scheme species map if necessary
        cache_file = os.path.join(self.input_dir, 'scheme_species_map.tab')
        if not os.path.exists(cache_file):
            try:
                scheme_species_map = pd.read_csv('https://raw.githubusercontent.com/tseemann/mlst/master/db/scheme_species_map.tab', sep='\t')
                scheme_species_map.to_csv(cache_file, sep='\t', index=False)
                logger.info("Downloaded and cached scheme_species_map.tab")
            except Exception as e:
                logger.error(f"Error downloading scheme_species_map.tab: {e}")
                raise
        else:
            scheme_species_map = pd.read_csv(cache_file, sep='\t')
            logger.info("Loaded cached scheme_species_map.tab")

        # Filter the dataframe to only the expected genus
        filtered_schemes = scheme_species_map[scheme_species_map['GENUS'] == expected_genus]
        if filtered_schemes.empty:
            logger.warning(f"No schemes found for genus '{expected_genus}' in scheme_species_map.tab")

        # Check if the scheme in mlst result partially matches with one or more schemes for the expected genus
        matched_schemes = '|'.join(filtered_schemes['#SCHEME'].astype(str).unique())
        if matched_schemes and any(mlst_result['scheme'].str.contains(matched_schemes)):
            # Set mlst_result['passed_mlst'] to True
            mlst_result['passed_mlst'] = True
            logger.info("MLST scheme matches the expected genus schemes.")
        else:
            # Set mlst_result['passed_mlst'] to False
            mlst_result['passed_mlst'] = False
            logger.warning("MLST scheme does not match the expected genus schemes.")

        # Take the first row and convert it to a dictionary after dropping the 'sample' column
        mlst_result = mlst_result.iloc[0].drop('sample').to_dict()

        self.qc_data[sample_name]['mlst'] = mlst_result

        self.qc_results[sample_name]['mlst'] = mlst_result['passed_mlst']

        self.qc_requirements[sample_name]['mlst'] = {'expected_genus': expected_genus}

        logger.info("MLST processing complete.")

    def check_assembly_scan(self, sample_name, maximum_contigs=500, minimum_n50=15000):
        """
        Check the quality of assembly scan results for a given sample.

        Updates self.qc_data[sample_name]['assembly_scan'] with the results.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        # Ensure genome size data is available
        if 'genome_size' not in self.qc_data[sample_name]:
            self.get_expected_genome_size(sample_name)

        data = self.qc_data[sample_name]['genome_size']

        # Get the file path
        file_path = os.path.join(self.input_dir, sample_name, 'main', 'assembler', f"{sample_name}.tsv")

        # Check the path exists
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Assembly scan data not found at {file_path}")

        # Read the file
        assembly_scan_df = pd.read_csv(file_path, sep='\t')

        if assembly_scan_df.shape[0] != 1:
            raise ValueError(f"Sample {sample_name}: Expected one row in assembly scan data, but got {assembly_scan_df.shape[0]} rows")

        # Take the first row and convert it to a dictionary after dropping the 'sample' column
        assembly_scan_results = assembly_scan_df.iloc[0].drop('sample').to_dict()

        # Add QC pass/fail flags
        assembly_scan_results['passed_contigs'] = assembly_scan_results['total_contig'] < maximum_contigs
        assembly_scan_results['passed_N50'] = assembly_scan_results['n50_contig_length'] > minimum_n50
        assembly_scan_results.update(data)

        # Calculate acceptable genome size range
        min_length = data['minimum_ungapped_length']
        max_length = data['maximum_ungapped_length']
        total_length = assembly_scan_results['total_contig_length']

        assembly_scan_results['passed_genome_size'] = (total_length > min_length) and (total_length < max_length)
        assembly_scan_results['passed_assembly_scan'] = all([
            assembly_scan_results['passed_contigs'],
            assembly_scan_results['passed_N50'],
            assembly_scan_results['passed_genome_size']
        ])

        self.qc_data[sample_name]['assembly_scan'] = assembly_scan_results

        self.qc_results[sample_name]['assembly_scan'] = assembly_scan_results['passed_assembly_scan']

        self.qc_requirements[sample_name]['assembly_scan'] = {
            'maximum_contigs': maximum_contigs,
            'minimum_n50': minimum_n50,
            'minimum_ungapped_length': min_length,
            'maximum_ungapped_length': max_length
        }

        logger.info("Assembly scan processing complete.")

    def check_fastp(self, sample_name, min_q30_bases=0.85, min_coverage=30):
        """
        Checks fastp quality control data for a given sample.

        Updates self.qc_data[sample_name]['fastp'] with the results.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Initialize qc_data, qc_results, qc_requirements for the sample if not already done
        if sample_name not in self.qc_data:
            self.qc_data[sample_name] = {'sample': sample_name}
        if sample_name not in self.qc_results:
            self.qc_results[sample_name] = {}
        if sample_name not in self.qc_requirements:
            self.qc_requirements[sample_name] = {}

        # Get the file path
        file_path = os.path.join(self.input_dir, sample_name, 'main', 'qc', 'summary', f"{sample_name}.fastp.json")

        # Check the path exists
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Fastp data not found at {file_path}")

        # Read the JSON file
        try:
            with open(file_path, 'r') as file:
                data = json.load(file)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {file_path}: {e}")
            raise

        # Create a dictionary with relevant metrics
        fastp_results = {
            'pre_filt_total_reads': int(data['summary']['before_filtering']['total_reads']),
            'pre_filt_total_bases': int(data['summary']['before_filtering']['total_bases']),
            'pre_filt_q30_rate': float(data['summary']['before_filtering']['q30_rate']),
            'pre_filt_gc': float(data['summary']['before_filtering']['gc_content']),
            'post_filt_total_reads': int(data['summary']['after_filtering']['total_reads']),
            'post_filt_total_bases': int(data['summary']['after_filtering']['total_bases']),
            'post_filt_q20_rate': float(data['summary']['after_filtering']['q20_rate']),
            'post_filt_q30_rate': float(data['summary']['after_filtering']['q30_rate']),
            'post_filt_gc': float(data['summary']['after_filtering']['gc_content']),
        }

        # Ensure assembly size is available
        if 'assembly_size' not in self.qc_data[sample_name]:
            self.get_assembly_size(sample_name)

        assembly_size = self.qc_data[sample_name]['assembly_size']

        # Compute coverage
        coverage = fastp_results['post_filt_total_bases'] / assembly_size['total_length']

        # Ensure coverage is computed correctly and handle potential division by zero
        try:
            coverage = fastp_results['post_filt_total_bases'] / assembly_size['total_length']
        except ZeroDivisionError:
            coverage = 0

        # Add the coverage to the dictionary
        fastp_results['coverage'] = round(coverage, 2)

        # Add a boolean for whether the Q30 bases are greater than min_q30_bases
        fastp_results['passed_q30_bases'] = fastp_results['post_filt_q30_rate'] > min_q30_bases

        # Add a boolean for whether the coverage is greater than min_coverage
        fastp_results['passed_coverage'] = coverage > min_coverage

        # Add a boolean for whether the fastp QC passed
        fastp_results['passed_fastp_QC'] = fastp_results['passed_q30_bases'] and fastp_results['passed_coverage']

        # Ensure all QC results are boolean
        fastp_results['passed_q30_bases'] = bool(fastp_results['passed_q30_bases'])
        fastp_results['passed_coverage'] = bool(fastp_results['passed_coverage'])
        fastp_results['passed_fastp_QC'] = bool(fastp_results['passed_fastp_QC'])

        self.qc_data[sample_name]['fastp'] = fastp_results

        self.qc_results[sample_name]['fastp'] = fastp_results['passed_fastp_QC']

        self.qc_requirements[sample_name]['fastp'] = {
            'min_q30_bases': min_q30_bases,
            'min_coverage': min_coverage
        }

        logger.info("Fastp processing complete.")

    def overall_qc(self, sample_name):
        """
        Determines the overall QC result for the current sample.
        """
        if not sample_name:
            raise ValueError("Sample name is not set. Please provide a sample name.")

        # Exclude 'sample' key if present
        results_values = [value for key, value in self.qc_results[sample_name].items()]

        # Replace NaN with False
        results_values = [bool(value) for value in results_values]

        self.qc_results[sample_name]['overall'] = all(results_values)

    def get_qc_results(self, output_prefix='qc_results'):
        """
        Returns the quality control results for all samples.

        Creates a TSV file with the QC results for each sample.
        """
        
        results_list = []
        for sample_name in self.sample_names:
            sample_results = self.qc_results.get(sample_name, {}).copy()
            if not sample_results:
                continue  # Skip samples with no results
            sample_results['sample'] = sample_name
            # Add columns for detected species
            bracken_species = self.qc_data[sample_name].get('bracken', {}).get('bracken_primary_species', 'N/A')
            mash_species = self.qc_data[sample_name].get('genome_size', {}).get('organism_name', 'N/A')
            sample_results['Detected species (Bracken)'] = bracken_species
            sample_results['Detected species (Mash)'] = mash_species
            results_list.append(sample_results)

        if not results_list:
            logger.warning("No QC results to write.")
            return pd.DataFrame()

        # Create a DataFrame from the list of dictionaries
        results_df = pd.DataFrame(results_list)

        # Replace NaN with False for boolean QC result columns
        qc_columns = ['bracken', 'mlst', 'checkm', 'assembly_scan', 'fastp', 'overall']
        for col in qc_columns:
            if col in results_df.columns:
                results_df[col] = results_df[col].fillna(False).astype(bool)

        # Reorder columns
        desired_order = ['sample', 'Detected species (Bracken)', 'Detected species (Mash)',
                        'bracken', 'mlst', 'checkm', 'assembly_scan', 'fastp', 'overall']
        # Ensure all desired columns are present
        existing_columns = [col for col in desired_order if col in results_df.columns]
        results_df = results_df.reindex(columns=existing_columns)


        # Write the results to file
        results_df.to_csv(f"{output_prefix}.tsv", sep='\t', index=False)

        # Return the DataFrame
        return results_df

    def get_qc_thresholds(self, output_prefix='qc_thresholds'):
        """
        Returns the quality control thresholds for all samples.
        """
        thresholds_list = []
        for sample_name in self.sample_names:
            sample_requirements = self.qc_requirements.get(sample_name, {}).copy()
            if not sample_requirements:
                continue  # Skip samples with no thresholds
            # Initialize a new dictionary for flattened parameters
            flattened_requirements = {'sample': sample_name}
            for check, params in sample_requirements.items():
                if check == 'sample':
                    continue
                if isinstance(params, dict):
                    for param_key, param_value in params.items():
                        # Create a new key combining the check and parameter name
                        new_key = f"{check}_{param_key}"
                        flattened_requirements[new_key] = param_value
                else:
                    # If params is not a dict, just add it directly
                    flattened_requirements[check] = params
            thresholds_list.append(flattened_requirements)

        if not thresholds_list:
            logger.warning("No QC thresholds to write.")
            return pd.DataFrame()

        # Create a DataFrame from the list of dictionaries
        thresholds_df = pd.DataFrame(thresholds_list)

        # Reorder columns to have 'sample' as the first column
        if 'sample' in thresholds_df.columns:
            cols = thresholds_df.columns.tolist()
            cols.insert(0, cols.pop(cols.index('sample')))
            thresholds_df = thresholds_df[cols]

        # Write the thresholds to file
        thresholds_df.to_csv(f"{output_prefix}.tsv", sep='\t', index=False)

        # Return the DataFrame
        return thresholds_df

# Define __all__ for explicit exports
__all__ = [
    'Genome',
]

![banner](https://github.com/maxlcummins/bactQC/raw/main/bactQC_banner.png)

**bactQC** is a comprehensive command-line tool designed for quality control (QC) of bacterial genome data. It integrates multiple QC checks, including Bracken, MLST, CheckM, Assembly Scan, and fastp, to ensure the integrity and quality of your genomic assemblies. Whether you're analyzing a single sample or multiple samples from Bactopia outputs, bactQC provides an efficient and user-friendly interface to streamline your QC workflow.

## Table of Contents

- [Description](#description)
- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Installation Steps](#installation-steps)
  - [Data Preparation](#data-preparation)
- [Usage](#usage)
  - [Run QC Analysis](#run-qc-analysis)
  - [Check Individual QC Metrics](#check-individual-qc-metrics)
    - [Get Assembly Size](#get-assembly-size)
    - [Check Bracken](#check-bracken)
    - [Check MLST](#check-mlst)
    - [Check CheckM](#check-checkm)
    - [Check Assembly Scan](#check-assembly-scan)
    - [Check FastP](#check-fastp)
- [Output](#output)
- [Examples](#examples)
  - [Running QC Analysis for a Single Sample](#running-qc-analysis-for-a-single-sample)
  - [Running QC Analysis for All Samples](#running-qc-analysis-for-all-samples)
  - [Checking Individual QC Metrics](#checking-individual-qc-metrics)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

## Description

bactQC is a robust tool for performing quality control on bacterial genome assemblies. By leveraging various bioinformatics tools, it provides a comprehensive assessment of genome quality, ensuring reliable downstream analyses. Key functionalities include:

- **Bracken Analysis:** Assess the abundance of primary and secondary species.
- **MLST Checking:** Validate multi-locus sequence typing results.
- **CheckM Evaluation:** Evaluate genome completeness and contamination.
- **Assembly Scan:** Analyze assembly metrics like contig counts and N50.
- **fastp Assessment:** Examine sequencing quality metrics post-filtering.

## Features

- **Automated QC Pipeline:** Run all quality checks with a single command.
- **Detailed Reporting:** Generates comprehensive TSV reports for results and thresholds.
- **Rich Console Output:** Enhanced terminal output with tables and emojis for better readability.
- **Modular Commands:** Execute individual QC checks as needed.
- **Customizable Thresholds:** Adjust QC parameters to fit specific project requirements.
- **Species-Specific Analysis:** Tailor QC thresholds based on detected species.

## Installation

### Prerequisites

- **Python 3.6 or higher**
- **pip** package installer

### Installation Steps

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/maxlcummins/bactQC.git
   cd bactQC
   ```

2. **Set Up a Virtual Environment (Optional but Recommended):**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   *If `requirements.txt` is not provided, install dependencies manually:*

   ```bash
   pip install pandas requests click rich emoji
   ```

4. **Install bactQC:**

   ```bash
   pip install .
   ```

   *Alternatively, you can run the CLI directly without installation:*

   ```bash
   python bactQC/cli.py
   ```

### Data Preparation

bactQC expects particular inputs generated by bactopia to run. Generate them as follows. If you want to run bactopia on lots of your own genomes, using a [sample sheet](https://bactopia.github.io/latest/tutorial/#multiple-samples-fofn) is best.

```
# Run bactopia's main workflow
bactopia -profile test,docker

# Run Bracken module
bactopia -profile docker --wf bracken --kraken2_db /Users/maxcummins/Documents/RDH/databases/k2_plus_pf_16gb --bactopia bactopia

# Run CheckM module
bactopia -profile docker --wf checkm --bactopia bactopia
```

## Usage

bactQC provides a command-line interface (CLI) with multiple commands to perform quality control on bacterial genome data.

### Run QC Analysis

Run all quality control checks for a specific sample or all samples in the input directory.

```bash
bactQC run [OPTIONS]
```

**Options:**

- `--sample_name TEXT`  
  Name of a sample to analyze.  
  Example: `--sample_name sample1`

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`  
  Example: `--input_dir /path/to/bactopia`

- `--min_primary_abundance FLOAT`  
  Minimum required abundance for the primary species.  
  Default: `0.80`

- `--min_completeness INTEGER`  
  Minimum required completeness threshold.  
  Default: `80`

- `--max_contamination INTEGER`  
  Maximum allowed contamination threshold.  
  Default: `10`

- `--maximum_contigs INTEGER`  
  Maximum allowed number of contigs.  
  Default: `500`

- `--minimum_n50 INTEGER`  
  Minimum required N50 contig length.  
  Default: `15000`

- `--min_q30_bases FLOAT`  
  Minimum required proportion of Q30 bases after filtering.  
  Default: `0.90`

- `--min_coverage INTEGER`  
  Minimum required coverage after filtering.  
  Default: `30`

#### Example

Analyze a specific sample:

```bash
bactQC run --sample_name sample1 --input_dir /path/to/bactopia
```

Analyze all samples in the default `bactopia` directory:

```bash
bactQC run
```

### Check Individual QC Metrics

bactQC also provides individual commands to perform specific QC checks. This is useful for debugging or when you only need to verify a particular aspect of your data.

#### Get Assembly Size

Retrieve the total contig length from assembler results.

```bash
bactQC get_assembly_size [OPTIONS]
```

**Options:**

- `--sample_name TEXT`  
  **Required.** Name of a sample to analyze.

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`

**Example:**

```bash
bactQC get_assembly_size --sample_name sample1
```

#### Check Bracken

Check Bracken results for a sample.

```bash
bactQC check_bracken [OPTIONS]
```

###  Usage

**Options:**

- `--sample_name TEXT`  
  **Required.** Name of a sample to analyze.

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`

- `--min_primary_abundance FLOAT`  
  Minimum required abundance for the primary species.  
  Default: `0.80`

**Example:**

```bash
bactQC check_bracken --sample_name sample1
```

#### Check MLST

Check MLST results for a sample.

```bash
bactQC check_mlst [OPTIONS]
```

**Options:**

- `--sample_name TEXT`  
  **Required.** Name of a sample to analyze.

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`

**Example:**

```bash
bactQC check_mlst --sample_name sample1
```

#### Check CheckM

Check CheckM results for a sample.

```bash
bactQC check_checkm [OPTIONS]
```

**Options:**

- `--sample_name TEXT`  
  **Required.** Name of a sample to analyze.

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`

- `--min_completeness INTEGER`  
  Minimum required completeness threshold.  
  Default: `80`

- `--max_contamination INTEGER`  
  Maximum allowed contamination threshold.  
  Default: `10`

**Example:**

```bash
bactQC check_checkm --sample_name sample1
```

#### Check Assembly Scan

Check assembly scan results for a sample.

```bash
bactQC check_assembly_scan [OPTIONS]
```

**Options:**

- `--sample_name TEXT`  
  **Required.** Name of a sample to analyze.

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`

- `--maximum_contigs INTEGER`  
  Maximum allowed number of contigs.  
  Default: `500`

- `--minimum_n50 INTEGER`  
  Minimum required N50 contig length.  
  Default: `15000`

**Example:**

```bash
bactQC check_assembly_scan --sample_name sample1
```

#### Check FastP

Check fastp quality control data for a sample.

```bash
bactQC check_fastp [OPTIONS]
```

**Options:**

- `--sample_name TEXT`  
  **Required.** Name of a sample to analyze.

- `--input_dir PATH`  
  Directory containing Bactopia outputs.  
  Default: `bactopia`

- `--min_q30_bases FLOAT`  
  Minimum required proportion of Q30 bases after filtering.  
  Default: `0.90`

- `--min_coverage INTEGER`  
  Minimum required coverage after filtering.  
  Default: `30`

**Example:**

```bash
bactQC check_fastp --sample_name sample1
```

## Output

bactQC generates two primary output files in TSV (Tab-Separated Values) format for each analyzed sample:

1. **QC Results:**
   - **Filename:** `<sample_name>_qc_results.tsv` or `BactQC_results.tsv` for multiple samples.
   - **Contents:** Contains the QC results for each sample, including status (Passed/Failed) for individual checks and detected species information.

2. **QC Thresholds:**
   - **Filename:** `<sample_name>_qc_thresholds.tsv` or `BactQC_thresholds.tsv` for multiple samples.
   - **Contents:** Contains the QC thresholds used for each check, which can be species-specific.

Additionally, individual commands display detailed QC metrics in the terminal using Rich tables with colored formatting and emojis for easy interpretation.

## Examples

### Running QC Analysis for a Single Sample

```bash
bactQC run --sample_name sample1 --input_dir /path/to/bactopia
```

**Output:**

- Displays ASCII art and a welcome message.
- Runs all QC checks with specified thresholds.
- Generates `sample1_qc_results.tsv` and `sample1_qc_thresholds.tsv`.
- Displays summarized QC thresholds and results in the terminal.

### Running QC Analysis for All Samples

```bash
bactQC run
```

**Output:**

- Processes all samples in the default `bactopia` directory.
- Generates `BactQC_results.tsv` and `BactQC_thresholds.tsv`.
- Displays summarized QC thresholds and results for all samples in the terminal.

### Checking Individual QC Metrics

Retrieve assembly size for a sample:

```bash
bactQC get_assembly_size --sample_name sample1
```

Check Bracken results:

```bash
bactQC check_bracken --sample_name sample1
```

Check MLST results:

```bash
bactQC check_mlst --sample_name sample1
```

Check CheckM results:

```bash
bactQC check_checkm --sample_name sample1
```

Check Assembly Scan results:

```bash
bactQC check_assembly_scan --sample_name sample1
```

Check FastP results:

```bash
bactQC check_fastp --sample_name sample1
```

## Contributing

Contributions are welcome! To contribute to bactQC, please follow these steps:

1. **Fork the Repository**

   Click the "Fork" button at the top-right corner of the repository page to create a forked copy of the repository.

2. **Clone the Forked Repository**

   ```bash
   git clone https://github.com/your-username/bactQC.git
   cd bactQC
   ```

3. **Create a New Branch**

   ```bash
   git checkout -b feature/YourFeature
   ```

4. **Make Your Changes**

   Implement your feature or bug fix. Ensure your code adheres to the project's coding standards.

5. **Commit Your Changes**

   ```bash
   git commit -m "Add feature: YourFeature"
   ```

6. **Push to Your Fork**

   ```bash
   git push origin feature/YourFeature
   ```

7. **Create a Pull Request**

   Navigate to the original repository and create a pull request from your forked repository.

Please ensure your contributions follow the Code of Conduct and Contributing Guidelines if available.

## License

This project is licensed under the MIT License.

## Contact

For questions, suggestions, or support, please open an issue on GitHub or contact the maintainer:

- **Maintainer:** Max L. Cummins
- **Email:** [max.l.cummins@gmail.com](mailto:max.l.cummins@gmail.com)

Thank you for using bactQC! 🦠🧬

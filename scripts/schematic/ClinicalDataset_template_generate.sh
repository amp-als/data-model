mamba activate amp-als
python scripts/schematic/schematic_client.py generate-manifest --data-type ClinicalDataset --schema-url https://raw.githubusercontent.com/amp-als/data-model/refs/heads/main/ALS.jsonld --output-format excel --out Dataset_template.xlsx


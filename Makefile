all: ALS.jsonld dist/ALS.yaml ALS.ttl dist/ALS.toon

ALS.jsonld: dist/ALS.yaml
	bb ./retold/retold as-jsonld --dir modules --out ALS.jsonld

SOURCES = header.yaml $(shell find modules -type f -name '*.yaml')

dist/ALS.yaml: $(SOURCES)
	yq eval-all '. as $$item ireduce ({}; . * $$item )' header.yaml modules/shared/*.yaml modules/**/*.yaml > merged.yaml
	yq 'del(.. | select(has("annotations")).annotations)' merged.yaml > merged_no_extra_meta.yaml
	yq 'del(.. | select(has("enum_range")).enum_range)' merged_no_extra_meta.yaml > merged_no_inlined_range.yaml
	yq 'del(.. | select(has("in_subset")).in_subset)' merged_no_inlined_range.yaml > dist/ALS.yaml
	rm -f merged*.yaml

ALS.ttl: dist/ALS.yaml
	gen-rdf dist/ALS.yaml > dist/ALS.ttl

dist/ALS.toon: dist/ALS.yaml
	yq -o=json '.' dist/ALS.yaml | npx @toon-format/cli > dist/ALS.toon


linkml_jsonld:
	gen-jsonld dist/ALS.yaml > dist/ALS_linkml.jsonld

# Compile certain json schemas with LinkML with selective import of props, enums, and template 
# LinkML output needs to be dereferenced bc Synapse doesn't suppport full JSON schema specs such as $defs
Dataset:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/shared/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/reference/data-types.yaml modules/omics/assays.yaml modules/reference/species.yaml modules/governance/portals.yaml modules/shared/common-enums.yaml > relevant_enums.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' header.yaml relevant_props.yaml relevant_enums.yaml modules/base/BaseDataset.yaml modules/mixins/DatasetMixins.yaml modules/portal/Dataset.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".Dataset | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-dataset"' tmp.json > json-schemas/Dataset.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/Dataset.json ---"

ClinicalDataset:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/shared/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/reference/data-types.yaml modules/reference/species.yaml modules/governance/portals.yaml modules/shared/common-enums.yaml > relevant_enums.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' header.yaml relevant_props.yaml relevant_enums.yaml modules/base/BaseDataset.yaml modules/mixins/DatasetMixins.yaml modules/clinical/domains.yaml modules/datasets/ClinicalDataset.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".ClinicalDataset | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-clinical-dataset"' tmp.json > json-schemas/ClinicalDataset.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/ClinicalDataset.json ---"

OmicDataset:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/shared/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/reference/data-types.yaml modules/omics/assays.yaml modules/omics/platforms.yaml modules/reference/species.yaml modules/governance/portals.yaml modules/shared/common-enums.yaml > relevant_enums.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' header.yaml relevant_props.yaml relevant_enums.yaml modules/base/BaseDataset.yaml modules/datasets/OmicDataset.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".OmicDataset | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-omic-dataset"' tmp.json > json-schemas/OmicDataset.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/OmicDataset.json ---"

File:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/shared/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/reference/data-types.yaml modules/omics/assays.yaml modules/reference/species.yaml modules/governance/portals.yaml modules/shared/common-enums.yaml > relevant_enums.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' header.yaml relevant_props.yaml relevant_enums.yaml modules/base/BaseFile.yaml modules/mixins/FileMixins.yaml modules/clinical/domains.yaml modules/shared/annotations.yaml modules/shared/analysis-methods.yaml modules/portal/File.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".File | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-file"' tmp.json > json-schemas/File.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/File.json ---"

ClinicalFile:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/shared/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/reference/data-types.yaml modules/reference/species.yaml modules/governance/portals.yaml modules/shared/common-enums.yaml > relevant_enums.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' header.yaml relevant_props.yaml relevant_enums.yaml modules/base/BaseFile.yaml modules/mixins/FileMixins.yaml modules/clinical/domains.yaml modules/clinical/data-types.yaml modules/shared/annotations.yaml modules/shared/analysis-methods.yaml modules/entities/ClinicalAssessment.yaml modules/datasets/ClinicalFile.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".ClinicalFile | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-clinical-file"' tmp.json > json-schemas/ClinicalFile.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/ClinicalFile.json ---"

OmicFile:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/shared/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/reference/data-types.yaml modules/omics/assays.yaml modules/omics/platforms.yaml modules/reference/species.yaml modules/governance/portals.yaml modules/shared/common-enums.yaml > relevant_enums.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' header.yaml relevant_props.yaml relevant_enums.yaml modules/base/BaseFile.yaml modules/mixins/FileMixins.yaml modules/omics/data-types.yaml modules/shared/annotations.yaml modules/shared/analysis-methods.yaml modules/datasets/OmicFile.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".OmicFile | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-omic-file"' tmp.json > json-schemas/OmicFile.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/OmicFile.json ---"

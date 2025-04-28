all: ALS.jsonld ALS.yaml ALS.ttl

ALS.jsonld:
	bb ./retold/retold as-jsonld --dir modules --out ALS.jsonld 

ALS.yaml:
	yq eval-all '. as $$item ireduce ({}; . * $$item )' header.yaml modules/props.yaml modules/**/*.yaml > merged.yaml
	yq 'del(.. | select(has("annotations")).annotations)' merged.yaml > merged_no_extra_meta.yaml
	yq 'del(.. | select(has("enum_range")).enum_range)' merged_no_extra_meta.yaml > merged_no_inlined_range.yaml
	yq 'del(.. | select(has("in_subset")).in_subset)' merged_no_inlined_range.yaml > dist/ALS.yaml
	rm -f merged*.yaml

ALS.ttl:
	make dist/ALS.yaml
	gen-rdf dist/ALS.yaml > dist/ALS.ttl

linkml_jsonld:
	gen-jsonld dist/ALS.yaml > dist/ALS_linkml.jsonld

# Compile certain json schemas with LinkML with selective import of props, enums, and template 
# LinkML output needs to be dereferenced bc Synapse doesn't suppport full JSON schema specs such as $defs
Dataset:
	yq '.slots |= with_entries(select(.value.in_subset[] == "portal"))' modules/props.yaml > relevant_props.yaml
	yq ea '. as $$item ireduce ({}; . * $$item )' modules/Data/Data.yaml modules/Assay/Assay.yaml modules/Sample/Species.yaml modules/DCC/Portal.yaml > relevant_enums.yaml
	cat header.yaml relevant_props.yaml relevant_enums.yaml modules/Template/Dataset.yaml > temp.yaml
	gen-json-schema --inline --no-metadata --title-from=title --not-closed temp.yaml > tmp.json
	json-dereference -s tmp.json -o tmp.json
	jq '."$$defs".Dataset | ."$$id"="https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered/org.synapse.ampals-dataset"' tmp.json > json-schemas/Dataset.json
	rm -f relevant_props.yaml relevant_enums.yaml temp.yaml tmp.json
	@echo "--- Saved json-schemas/Dataset.json ---"

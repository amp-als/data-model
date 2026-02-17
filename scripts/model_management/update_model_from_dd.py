#!/usr/bin/env python
# coding: utf-8

"""
This script updates the data model from the data dictionaries.
"""

import csv
import hashlib
import json
import os
import re
import signal
import sys
import argparse
import subprocess
import tempfile
from difflib import SequenceMatcher
from ruamel.yaml import YAML

# --- Helper Functions ---

def connect_to_synapse():
    """Connect to Synapse using env token or default credential discovery."""
    try:
        import synapseclient
    except ImportError as e:
        raise RuntimeError(
            "synapseclient is required for --generate-view-to-class mode. "
            "Install it with `pip install synapseclient`."
        ) from e

    syn = synapseclient.Synapse()
    auth_token = os.getenv("SYNAPSE_AUTH_TOKEN")
    if auth_token:
        syn.login(authToken=auth_token)
        print("Connected to Synapse (using SYNAPSE_AUTH_TOKEN)")
    else:
        syn.login()
        print("Connected to Synapse (using default credentials)")
    return syn

def to_camel_case(snake_str):
    """Converts snake_case to camelCase."""
    if not snake_str:
        return ""
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def normalize_view_name(view_name):
    """Normalize view names for robust matching."""
    return str(view_name).strip().lower()

def is_view_like_name(value):
    """Return True if a string looks like a view identifier."""
    return bool(
        re.match(
            r'^(?:v|ct)_allals_(?:as|pr|pv)_[a-z0-9_]+$',
            normalize_view_name(value),
        )
    )

def parse_data_dictionary(file_path):
    """Parses a data dictionary CSV file."""
    data = {}
    current_view = None
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader) # Skip header
            for row in reader:
                if not row or not any(row):
                    continue
                view_name = row[0].strip() if len(row) > 0 else ""
                if view_name:
                    current_view = view_name
                    if current_view not in data:
                        data[current_view] = []
                
                if current_view and len(row) > 1 and row[1]:
                    field_info = {
                        'field': row[1],
                        'description': row[2] if len(row) > 2 else "",
                        'values': row[3] if len(row) > 3 else ""
                    }
                    data[current_view].append(field_info)
    except (IOError, StopIteration) as e:
        print(f"Error reading data dictionary {file_path}: {e}", file=sys.stderr)
    return data

def parse_view_to_class_mapping(file_path):
    """Parses the view_to_class_mapping.md file."""
    mapping = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if "|" not in line:
                    continue
                parts = [p.strip().strip("`") for p in line.split("|")[1:-1]]
                if len(parts) < 2:
                    continue
                view_name = parts[0]
                # Supports both:
                # 1) | view_name | class_name |
                # 2) | view_name | form_name | class_name |
                class_name = parts[2] if len(parts) >= 3 else parts[1]
                class_name = class_name.split("(")[0].strip()
                if not view_name or not class_name:
                    continue
                if not re.match(r'^(?:v|ct)_allals_(?:as|pr|pv)_[a-z0-9_]+$', normalize_view_name(view_name)):
                    continue
                mapping[normalize_view_name(view_name)] = class_name
    except IOError as e:
        print(f"Error reading mapping file {file_path}: {e}", file=sys.stderr)
    return mapping

def parse_view_to_form_name_mapping(file_path):
    """Parse markdown mapping and return normalized view_name -> form_name."""
    mapping = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if "|" not in line:
                    continue
                parts = [p.strip().strip("`") for p in line.split("|")[1:-1]]
                if len(parts) < 2:
                    continue
                view_name = parts[0]
                # For 3-column format this is form name; for 2-column fallback this may be class name.
                form_name = parts[1]
                if not view_name or not form_name:
                    continue
                norm_view = normalize_view_name(view_name)
                if not re.match(r'^(?:v|ct)_allals_(?:as|pr|pv)_[a-z0-9_]+$', norm_view):
                    continue
                mapping[norm_view] = form_name
    except IOError as e:
        print(f"Error reading mapping file {file_path}: {e}", file=sys.stderr)
    return mapping

def derive_view_name_from_filename(filename):
    """
    Extract view name from CSV filename, e.g.:
    v_ALLALS_AS_ASSEDEMOG.csv -> v_ALLALS_AS_ASSEDEMOG
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    if re.match(r'^v_ALLALS_(?:AS|PR|PV)_[A-Z0-9_]+$', base, re.IGNORECASE):
        return base.upper()
    return None

def form_name_to_class_name(form_name):
    """Convert a form name into a LinkML-friendly PascalCase class name."""
    cleaned = re.sub(r'[^A-Za-z0-9]+', ' ', str(form_name)).strip()
    if not cleaned:
        return ""
    parts = [p for p in cleaned.split() if p]
    class_name = ''.join(p[0].upper() + p[1:] for p in parts)
    if class_name and class_name[0].isdigit():
        class_name = f"Form{class_name}"
    return class_name

def extract_form_name_from_csv(file_path):
    """Extract form_name or Form Name value from first data row of a CSV."""
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader)
            if not header:
                return None, "empty_header"

            header_map = {str(h).strip().lower(): i for i, h in enumerate(header)}
            idx = None
            for candidate in ("form_name", "form name"):
                if candidate in header_map:
                    idx = header_map[candidate]
                    break

            if idx is None:
                return None, "missing_form_name_column"

            try:
                row = next(reader)
            except StopIteration:
                return None, "empty_after_header"

            if idx >= len(row):
                return None, "missing_form_name_value"

            value = str(row[idx]).strip()
            if not value:
                return None, "blank_form_name"

            return value, None
    except Exception as e:
        return None, str(e)

def download_folder_csvs(syn, folder_id, dataset_label, downloads_dir):
    """Download all CSV files from a Synapse folder to downloads/<dataset_label>."""
    target_dir = os.path.join(downloads_dir, dataset_label)
    os.makedirs(target_dir, exist_ok=True)

    downloaded_files = []
    children = list(syn.getChildren(folder_id, includeTypes=["file"]))
    for child in children:
        file_name = child.get("name", "")
        if not file_name.lower().endswith(".csv"):
            continue

        syn_id = child["id"]
        try:
            entity = syn.get(syn_id, downloadLocation=target_dir)
            downloaded_files.append(entity.path)
        except Exception as e:
            print(f"Warning: Failed to download {syn_id} ({file_name}): {e}", file=sys.stderr)

    return downloaded_files

def write_view_to_class_markdown(mapping_rows, output_path):
    """Write generated view->form->class mapping to a markdown table."""
    lines = [
        "# View to Class Mapping\n",
        "\n",
        "| View Name | Form Name | Class Name |\n",
        "| --- | --- | --- |\n",
    ]

    for row in sorted(mapping_rows, key=lambda r: r["view_name"]):
        lines.append(
            f"| `{row['view_name']}` | `{row['form_name']}` | `{row['class_name']}` |\n"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def generate_view_to_class_mapping_from_synapse(assess_folder_id, prevent_folder_id, downloads_dir, output_path):
    """Download staging CSVs and generate a markdown mapping file."""
    print("Generating view_to_class mapping from Synapse staging folders...")
    syn = connect_to_synapse()

    downloads_dir = os.path.abspath(downloads_dir)
    os.makedirs(downloads_dir, exist_ok=True)

    all_rows = []
    seen_view_to_class = {}

    folder_specs = [
        ("ASSESS", assess_folder_id),
        ("PREVENT", prevent_folder_id),
    ]

    for dataset_label, folder_id in folder_specs:
        print(f"Downloading CSVs from {dataset_label} staging folder: {folder_id}")
        csv_files = download_folder_csvs(syn, folder_id, dataset_label, downloads_dir)
        print(f"  Downloaded {len(csv_files)} CSV file(s) to {os.path.join(downloads_dir, dataset_label)}")

        for file_path in csv_files:
            filename = os.path.basename(file_path)
            view_name = derive_view_name_from_filename(filename)
            if not view_name:
                print(f"  Warning: Could not derive view name from filename '{filename}'. Skipping.", file=sys.stderr)
                continue

            form_name, err = extract_form_name_from_csv(file_path)
            if err:
                print(f"  Warning: Could not extract form name from '{filename}' ({err}). Skipping.", file=sys.stderr)
                continue

            class_name = form_name_to_class_name(form_name)
            if not class_name:
                print(f"  Warning: Could not generate class name from form '{form_name}' in '{filename}'. Skipping.", file=sys.stderr)
                continue

            if view_name in seen_view_to_class and seen_view_to_class[view_name] != class_name:
                print(
                    f"  Warning: Duplicate view '{view_name}' has conflicting class names "
                    f"('{seen_view_to_class[view_name]}' vs '{class_name}'). Keeping first.",
                    file=sys.stderr,
                )
                continue

            if view_name not in seen_view_to_class:
                seen_view_to_class[view_name] = class_name
                all_rows.append(
                    {
                        "view_name": view_name,
                        "form_name": form_name,
                        "class_name": class_name,
                    }
                )

    write_view_to_class_markdown(all_rows, output_path)
    print(f"Generated mapping file: {output_path}")
    print(f"Total mapping rows: {len(all_rows)}")
    return output_path

def resolve_data_dictionary_paths(args):
    """
    Resolve ASSESS/PREVENT data dictionary CSV paths from either:
    1) Synapse IDs (--assess-dd-synid/--prevent-dd-synid), or
    2) Local dd-dir (legacy behavior with expected filenames).
    """
    dd_paths = {}

    if args.assess_dd_synid and args.prevent_dd_synid:
        print("Downloading data dictionaries from Synapse IDs...")
        syn = connect_to_synapse()
        dd_dir = os.path.abspath(args.dd_downloads_dir)
        os.makedirs(dd_dir, exist_ok=True)

        synid_map = {
            "ASSESS": args.assess_dd_synid,
            "PREVENT": args.prevent_dd_synid,
        }
        for dataset, syn_id in synid_map.items():
            try:
                entity = syn.get(syn_id, downloadLocation=dd_dir)
                dd_paths[dataset] = entity.path
                print(f"  Downloaded {dataset} DD: {entity.path}")
            except Exception as e:
                raise RuntimeError(
                    f"Failed to download {dataset} DD from {syn_id}: {e}"
                ) from e
        return dd_paths

    if args.dd_dir:
        dd_paths["ASSESS"] = os.path.join(
            args.dd_dir, "ASSESS", "ASSESS_DATA_DICTIONARY_OCTOBER_28.csv"
        )
        dd_paths["PREVENT"] = os.path.join(
            args.dd_dir, "PREVENT", "PREVENT_DATA_DICTIONARY_OCTOBER_28.csv"
        )
        return dd_paths

    raise RuntimeError(
        "Data dictionary source not provided. Use either --dd-dir or both "
        "--assess-dd-synid and --prevent-dd-synid."
    )

def infer_class_description(view_name, form_name):
    """
    Choose class description from trusted metadata rather than generated text.
    Priority:
    1) Form name from mapping table
    2) View name
    """
    if form_name and str(form_name).strip():
        return str(form_name).strip()
    return str(view_name).strip()

def add_merge_note_to_class_description(class_def, mapped_class_name, view_name, form_name):
    """Append an idempotent merge note when a view/class is merged into an existing class."""
    merge_label = str(form_name).strip() if form_name and str(form_name).strip() else mapped_class_name
    note = f"Merged source: {merge_label} ({view_name})"

    existing_desc = str(class_def.get("description", "") or "").strip()
    if note in existing_desc:
        return

    if existing_desc:
        class_def["description"] = f"{existing_desc}\n{note}"
    else:
        class_def["description"] = note

def normalize_value_token(value):
    if not value:
        return ""
    return str(value).strip().lower()

def parse_values_column(values_str):
    """Split raw DD values into cleaned tokens."""
    if not values_str or not str(values_str).strip():
        return []
    tokens = re.split(r'[;,]', str(values_str))
    cleaned = [t.strip() for t in tokens if t and t.strip()]
    return cleaned

def is_boolean_values(values, rule):
    tokens = {normalize_value_token(v) for v in values}
    if rule == "strict":
        return tokens == {"true", "false"}
    if rule == "normalize":
        normalized = {"true", "false", "yes", "no", "y", "n", "1", "0"}
        return tokens.issubset(normalized) and tokens
    return False

def compute_args_signature(args, proposal_path):
    relevant = {
        "mode": args.mode,
        "ai_provider": args.ai_provider,
        "enum_strategy": args.enum_strategy,
        "boolean_rule": args.boolean_rule,
        "use_gemini_review": args.use_gemini_review,
        "proposal_path": os.path.abspath(proposal_path),
    }
    serialized = json.dumps(relevant, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()

def load_checkpoint(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_checkpoint(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

stop_requested = False

def _signal_handler(signum, frame):
    global stop_requested
    stop_requested = True

PROPOSAL_COLUMNS = [
    "item_key",
    "view_name",
    "form_name",
    "field_name",
    "mapped_class",
    "target_file",
    "action",
    "attribute_name",
    "attribute_range",
    "enum_action",
    "enum_name",
    "enum_values",
    "values_raw",
    "reason",
    "status",
    "approved",
]


def compute_item_key(view_name, field_name, target_class):
    return f"{normalize_view_name(view_name)}|{field_name}|{normalize_class_name(target_class)}"


def load_existing_proposal_keys(path):
    if not os.path.exists(path):
        return set()
    keys = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("item_key")
                if key:
                    keys.add(key)
    except Exception:
        pass
    return keys


def build_enum_catalog(yaml_files):
    catalog = []
    seen_names = set()
    for path, data in yaml_files.items():
        if not isinstance(data, dict):
            continue
        enums = data.get("enums")
        if not isinstance(enums, dict):
            continue
        for name, enum_def in enums.items():
            if not isinstance(enum_def, dict):
                continue
            values = enum_def.get("permissible_values", [])
            normalized = set()
            raw_values = []
            for member in values:
                if isinstance(member, dict):
                    label = member.get("name") or member.get("value")
                else:
                    label = member
                if label:
                    raw = str(label).strip()
                    normalized.add(normalize_value_token(raw))
                    raw_values.append(raw)
            catalog.append(
                {
                    "name": name,
                    "file": path,
                    "value_set": frozenset(normalized),
                    "raw_values": list(dict.fromkeys(raw_values)),
                }
            )
            seen_names.add(name)
    return catalog


def find_matching_enum(values, catalog):
    target_set = frozenset(normalize_value_token(v) for v in values)
    if not target_set:
        return None
    for entry in catalog:
        if entry["value_set"] == target_set:
            return entry
    return None


def suggest_enum_name(class_name, attribute_name, existing_names):
    parts = []
    for value in (class_name, attribute_name):
        cleaned = re.sub(r"[^A-Za-z0-9]+", "", value.title())
        if cleaned:
            parts.append(cleaned)
    base = "".join(parts) or "Attribute"
    name = f"{base}Values"
    counter = 1
    while name in existing_names:
        counter += 1
        name = f"{base}Values{counter}"
    existing_names.add(name)
    return name


def ensure_enum_definition(yaml_files, target_file, enum_name, values):
    data = yaml_files.get(target_file)
    if data is None:
        yaml_files[target_file] = {}
        data = yaml_files[target_file]
    enums = data.get("enums")
    if enums is None:
        enums = {}
        data["enums"] = enums
    if enum_name in enums:
        return
    members = []
    for value in values:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
        member_name = cleaned or "value"
        members.append({"name": member_name, "description": value})
    enums[enum_name] = {"description": f"Values for {enum_name}", "permissible_values": members}


def determine_attribute_range(
    args,
    field,
    base_range,
    target_class_name,
    target_file,
    yaml_files,
    enum_catalog,
    existing_enum_names,
):
    values = parse_values_column(field.get("values", ""))
    if not values:
        return base_range, "none", None
    if is_boolean_values(values, args.boolean_rule):
        return "boolean", "boolean", None
    if args.enum_strategy == "keep-string":
        return base_range, "none", None
    normalized_values = [v for v in values if v]
    if not normalized_values:
        return "string", "none", None
    value_set = frozenset(normalize_value_token(v) for v in normalized_values)
    matching_enum = None
    if args.enum_strategy == "reuse-first":
        matching_enum = find_matching_enum(normalized_values, enum_catalog)
    if matching_enum and args.enum_strategy == "reuse-first":
        return matching_enum["name"], "reuse", matching_enum
    enum_name = suggest_enum_name(
        target_class_name, to_camel_case(field.get("field", "")), existing_enum_names
    )
    ensure_enum_definition(yaml_files, target_file, enum_name, normalized_values)
    new_entry = {
        "name": enum_name,
        "file": target_file,
        "value_set": value_set,
        "raw_values": normalized_values,
    }
    enum_catalog.append(new_entry)
    existing_enum_names.add(enum_name)
    return enum_name, "create", new_entry


def open_proposal_writer(path, resume):
    mode = "a" if resume and os.path.exists(path) else "w"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    f = open(path, mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=PROPOSAL_COLUMNS)
    if mode == "w":
        writer.writeheader()
    return writer, f


def _replace_class_reference_in_attr(attr_def, old_class_name, new_class_name):
    """Replace class references in a LinkML attribute-like object."""
    if not isinstance(attr_def, dict):
        return
    if attr_def.get("range") == old_class_name:
        attr_def["range"] = new_class_name
    any_of = attr_def.get("any_of")
    if isinstance(any_of, list):
        for option in any_of:
            if isinstance(option, dict) and option.get("range") == old_class_name:
                option["range"] = new_class_name

def rename_class_and_references(yaml_files, old_class_name, new_class_name):
    """
    Rename an existing class key and update common class references across model files.
    Returns (renamed, renamed_path, renamed_class_def, touched_paths, message).
    """
    if old_class_name == new_class_name:
        return False, None, None, [], "old_and_new_class_names_are_same"

    old_path, old_existing_name, old_class_def = find_class_in_yaml(yaml_files, old_class_name, loose=True)
    if not old_path:
        return False, None, None, [], "source_class_not_found"

    new_path, new_existing_name, _ = find_class_in_yaml(yaml_files, new_class_name, loose=False)
    if new_path and normalize_class_name(new_existing_name) != normalize_class_name(old_existing_name):
        return False, None, None, [], "target_class_name_already_exists"

    classes_block = yaml_files[old_path].get("classes", {})
    moved_def = classes_block.pop(old_existing_name)
    classes_block[new_class_name] = moved_def
    touched_paths = {old_path}

    for path, data in yaml_files.items():
        if not isinstance(data, dict):
            continue

        classes = data.get("classes")
        if isinstance(classes, dict):
            for _, class_def in classes.items():
                if not isinstance(class_def, dict):
                    continue
                if class_def.get("is_a") == old_existing_name:
                    class_def["is_a"] = new_class_name
                    touched_paths.add(path)
                mixins = class_def.get("mixins")
                if isinstance(mixins, list):
                    new_mixins = [
                        new_class_name if m == old_existing_name else m for m in mixins
                    ]
                    if new_mixins != mixins:
                        class_def["mixins"] = new_mixins
                        touched_paths.add(path)
                attrs = class_def.get("attributes")
                if isinstance(attrs, dict):
                    before = json.dumps(attrs, sort_keys=True, default=str)
                    for _, attr_def in attrs.items():
                        _replace_class_reference_in_attr(attr_def, old_existing_name, new_class_name)
                    after = json.dumps(attrs, sort_keys=True, default=str)
                    if before != after:
                        touched_paths.add(path)

        slots = data.get("slots")
        if isinstance(slots, dict):
            before = json.dumps(slots, sort_keys=True, default=str)
            for _, slot_def in slots.items():
                _replace_class_reference_in_attr(slot_def, old_existing_name, new_class_name)
            after = json.dumps(slots, sort_keys=True, default=str)
            if before != after:
                touched_paths.add(path)

    return True, old_path, moved_def, sorted(touched_paths), "renamed"

def load_yaml_files(modules_dir):
    """Loads all YAML files from the modules directory."""
    yaml_data = {}
    yaml = YAML()
    for root, _, files in os.walk(modules_dir):
        for file in files:
            if file.endswith(".yaml") or file.endswith(".yml"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        yaml_data[file_path] = yaml.load(f)
                except Exception as e:
                    print(f"Error loading YAML file {file_path}: {e}", file=sys.stderr)
    return yaml_data

def check_gemini_available():
    """Check if gemini CLI is available."""
    try:
        result = subprocess.run(["gemini", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0 or "gemini" in (result.stdout + result.stderr).lower()
    except Exception:
        return False

def check_codex_available():
    """Check if codex CLI is available."""
    try:
        result = subprocess.run(["codex", "--help"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0 or "codex" in (result.stdout + result.stderr).lower()
    except Exception:
        return False

def _parse_json_from_model_output(output):
    """Parse JSON payload from model output."""
    if not output:
        return None
    output = output.strip()
    if "```json" in output:
        m = re.search(r"```json\s*(\{.*?\})\s*```", output, re.DOTALL)
        if m:
            output = m.group(1)
    elif "```" in output:
        m = re.search(r"```\s*(\{.*?\})\s*```", output, re.DOTALL)
        if m:
            output = m.group(1)

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", output, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None

def run_gemini_json(prompt, timeout=60):
    """Run gemini CLI and parse JSON response."""
    try:
        result = subprocess.run(
            ["gemini", "--yolo", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err_preview = (result.stderr or result.stdout or "").strip().splitlines()
            if err_preview:
                print(f"[AI] Gemini failed: {err_preview[0]}")
            else:
                print("[AI] Gemini failed with non-zero exit code.")
            return None
        return _parse_json_from_model_output(result.stdout)
    except Exception:
        return None
    return None

def run_codex_json(prompt, timeout=60):
    """
    Run codex CLI and parse JSON response.
    Uses stdin to avoid quoting issues with long prompts.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="codex_last_msg_", suffix=".txt", delete=False) as tf:
            tmp_path = tf.name

        # codex exec is the non-interactive interface for this CLI.
        # Use "-" to read prompt from stdin and write final model message to tmp file.
        result = subprocess.run(
            [
                "codex",
                "exec",
                "-",
                "-s",
                "read-only",
                "-o",
                tmp_path,
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # Prefer the explicit last message output file.
        if tmp_path and os.path.exists(tmp_path):
            with open(tmp_path, "r", encoding="utf-8") as f:
                parsed = _parse_json_from_model_output(f.read())
            if isinstance(parsed, dict):
                return parsed

        # Fallback: parse stdout directly if available.
        parsed_stdout = _parse_json_from_model_output(result.stdout)
        if isinstance(parsed_stdout, dict):
            return parsed_stdout

        # If we get here, no parseable JSON was produced.
        err_preview = (result.stderr or result.stdout or "").strip().splitlines()
        if err_preview:
            status = f"(exit={result.returncode})"
            print(f"[AI Fallback] Codex produced no parseable JSON {status}: {err_preview[0]}")
        else:
            print(f"[AI Fallback] Codex produced no parseable JSON (exit={result.returncode}).")
    except Exception:
        print("[AI Fallback] Codex execution raised an exception.")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return None

def run_ai_json(prompt, provider="gemini", timeout=60, use_codex_fallback=False, codex_timeout=60):
    """
    Run AI suggestion call(s) and return parsed JSON.
    Provider can be "gemini" or "codex".
    If provider is gemini, optional codex fallback can be enabled.
    Returns (parsed_json_or_none, source_label).
    """
    if provider == "codex":
        parsed_codex = run_codex_json(prompt, timeout=codex_timeout)
        if isinstance(parsed_codex, dict):
            return parsed_codex, "codex"
        return None, "none"

    parsed = run_gemini_json(prompt, timeout=timeout)
    if isinstance(parsed, dict):
        return parsed, "gemini"

    if use_codex_fallback:
        parsed_codex = run_codex_json(prompt, timeout=codex_timeout)
        if isinstance(parsed_codex, dict):
            return parsed_codex, "codex"

    return None, "none"

def prompt_confirm(message):
    """Ask user to confirm a single proposed change."""
    while True:
        response = input(f"{message} [y/n]: ").strip().lower()
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please answer y or n.")

def prompt_review_action(message):
    """Ask user to accept, reject, or provide feedback for a proposed change."""
    while True:
        response = input(f"{message} [y=accept / n=skip / f=feedback]: ").strip().lower()
        if response in ("y", "yes"):
            return "accept"
        if response in ("n", "no"):
            return "skip"
        if response in ("f", "feedback"):
            return "feedback"
        print("Please answer y, n, or f.")

def sanitize_filename_from_class_name(class_name):
    """Convert class name to a stable YAML filename."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", class_name).strip("_")
    return slug.lower() + ".yaml"

def normalize_class_name(value):
    """Normalize class name for looser matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())

def class_name_stem(value):
    """Remove common trailing dataset qualifiers to improve matching."""
    norm = normalize_class_name(value)
    for suffix in ("assess", "prevent"):
        if norm.endswith(suffix):
            return norm[: -len(suffix)]
    return norm

def choose_grouped_assessment_file(modules_dir, yaml_files, class_name):
    """
    Choose default file for newly created assessment classes.

    Strategy:
    1) Place with the most similar existing class under modules/clinical/assessments.
    2) If no strong match exists, place in a shared fallback assessment file.
    """
    modules_abs = os.path.abspath(modules_dir)
    target_norm = class_name_stem(class_name)
    best = None

    for path, data in yaml_files.items():
        if not data or "classes" not in data:
            continue
        rel = os.path.relpath(path, modules_abs).replace("\\", "/")
        if not rel.startswith("clinical/assessments/"):
            continue

        file_best = 0.0
        for existing_name in data["classes"].keys():
            score = SequenceMatcher(None, target_norm, class_name_stem(existing_name)).ratio()
            if score > file_best:
                file_best = score

        if best is None or file_best > best[0]:
            best = (file_best, path)

    if best and best[0] >= 0.62:
        return best[1]

    return os.path.join(modules_dir, "clinical", "assessments", "other_generated_assessments.yaml")

def persist_yaml_file(path, data, dry_run=False):
    """Persist one YAML file immediately."""
    if dry_run:
        return
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def run_assess_mode(
    args,
    view_to_class,
    view_to_form_name,
    all_dd_data,
    yaml_files,
    checkpoint_root,
    mode_checkpoint,
    args_signature,
):
    signal.signal(signal.SIGINT, _signal_handler)
    global stop_requested
    stop_requested = False

    existing_keys = load_existing_proposal_keys(args.proposal_path)
    completed_keys = set(mode_checkpoint.get("completed_keys", []))
    completed_keys |= existing_keys
    processed_count = mode_checkpoint.get("processed_count", 0)
    def persist_checkpoint_state():
        mode_checkpoint["completed_keys"] = sorted(completed_keys)
        mode_checkpoint["processed_count"] = processed_count
        mode_checkpoint["args_signature"] = args_signature
        checkpoint_root["modes"][args.mode] = mode_checkpoint
        save_checkpoint(args.checkpoint_path, checkpoint_root)

    resume_file_exists = os.path.exists(args.proposal_path)
    writer, handle = open_proposal_writer(args.proposal_path, args.resume and resume_file_exists)
    enum_catalog = build_enum_catalog(yaml_files)
    existing_enum_names = {entry["name"] for entry in enum_catalog}
    rows_written = 0
    pause_counter = 0

    try:
        for view_name in sorted(all_dd_data.keys()):
            if stop_requested:
                break
            normalized_view = normalize_view_name(view_name)
            if normalized_view not in view_to_class:
                continue
            mapped_class = view_to_class[normalized_view]
            mapped_form_name = view_to_form_name.get(normalized_view, "")
            found_path, found_class_name, found_class_def = find_class_in_yaml(
                yaml_files, mapped_class, loose=True
            )
            class_exists = bool(found_path and found_class_name)
            target_class_name = found_class_name if class_exists else mapped_class
            if class_exists:
                target_file = found_path
                attributes = found_class_def.get("attributes", {}) if found_class_def else {}
            else:
                target_file = choose_grouped_assessment_file(
                    args.modules_dir, yaml_files, mapped_class
                )
                attributes = {}

            attr_names = set(attributes.keys()) if isinstance(attributes, dict) else set()
            closest_candidate = (
                None if class_exists else find_closest_class_candidate(yaml_files, mapped_class)
            )

            for field in all_dd_data.get(view_name, []):
                if stop_requested:
                    break
                raw_field = field.get("field", "")
                attr_name = to_camel_case(raw_field)
                if not attr_name:
                    continue
                item_key = compute_item_key(view_name, attr_name, target_class_name)
                if item_key in completed_keys:
                    continue

                field_values = parse_values_column(field.get("values", ""))
                enum_action = "none"
                enum_name = ""
                attribute_range = "string"

                if is_boolean_values(field_values, args.boolean_rule):
                    attribute_range = "boolean"
                elif field_values and args.enum_strategy != "keep-string":
                    normalized_values = [v for v in field_values if v]
                    value_set = frozenset(normalize_value_token(v) for v in normalized_values)
                    matching_enum = None
                    if args.enum_strategy == "reuse-first":
                        matching_enum = find_matching_enum(normalized_values, enum_catalog)
                    if matching_enum and args.enum_strategy == "reuse-first":
                        attribute_range = matching_enum["name"]
                        enum_action = "reuse"
                        enum_name = matching_enum["name"]
                    else:
                        enum_action = "create"
                        enum_name = suggest_enum_name(target_class_name, attr_name, existing_enum_names)
                        attribute_range = enum_name
                        enum_catalog.append(
                            {
                                "name": enum_name,
                                "file": target_file,
                                "value_set": value_set,
                                "raw_values": normalized_values,
                            }
                        )
                # status metadata
                if class_exists:
                    if attr_name in attr_names:
                        completed_keys.add(item_key)
                        continue
                    status = "new_attribute"
                    action = "add_attribute"
                    reason = (
                        f"Class '{target_class_name}' exists in {target_file}; attribute '{attr_name}' missing."
                    )
                else:
                    status = "new_class"
                    action = "create_class"
                    if closest_candidate:
                        reason = (
                            f"Mapped '{mapped_class}' missing; closest candidate "
                            f"'{closest_candidate['class_name']}' ({closest_candidate['file']})."
                        )
                    else:
                        reason = f"Mapped class '{mapped_class}' missing in modules; will create."

                row = {
                    "item_key": item_key,
                    "view_name": view_name,
                    "form_name": mapped_form_name,
                    "field_name": raw_field,
                    "mapped_class": mapped_class,
                    "target_file": target_file,
                    "action": action,
                    "attribute_name": attr_name,
                    "attribute_range": attribute_range,
                    "enum_action": enum_action,
                    "enum_name": enum_name,
                    "enum_values": json.dumps(field_values),
                    "values_raw": field.get("values", ""),
                    "reason": reason,
                    "status": status,
                    "approved": "false",
                }
                writer.writerow(row)
                handle.flush()
                rows_written += 1
                pause_counter += 1
                processed_count += 1
                existing_keys.add(item_key)
                completed_keys.add(item_key)

                persist_checkpoint_state()

                print(
                    f"    [Assess] queued {status} '{attr_name}' for class '{target_class_name}' "
                    f"({target_file})"
                )

                if args.pause_after and pause_counter >= args.pause_after:
                    print(f"    [Assess] pause triggered after {pause_counter} rows.")
                    stop_requested = True
                    break
            if stop_requested:
                break
    finally:
        handle.close()

    persist_checkpoint_state()

    if stop_requested:
        print(f"[Assess] Process paused. Run with --resume to continue from {args.proposal_path}.")
    else:
        print(f"[Assess] Proposal ready ({rows_written} new rows) at {args.proposal_path}.")
def find_class_in_yaml(yaml_files, class_name, loose=True):
    """Find class definition location with exact then optional loose matching."""
    # Exact match first
    for path, data in yaml_files.items():
        if data and "classes" in data and class_name in data["classes"]:
            return path, class_name, data["classes"][class_name]

    if not loose:
        return None, None, None

    # Case-insensitive exact key match
    target_lower = str(class_name).lower()
    for path, data in yaml_files.items():
        if not data or "classes" not in data:
            continue
        for existing_name, class_def in data["classes"].items():
            if str(existing_name).lower() == target_lower:
                return path, existing_name, class_def

    # Normalized/stem-based and fuzzy matching
    target_norm = normalize_class_name(class_name)
    target_stem = class_name_stem(class_name)
    best = None
    for path, data in yaml_files.items():
        if not data or "classes" not in data:
            continue
        for existing_name, class_def in data["classes"].items():
            existing_norm = normalize_class_name(existing_name)
            existing_stem = class_name_stem(existing_name)
            if not existing_norm:
                continue
            if target_norm == existing_norm or (target_stem and target_stem == existing_stem):
                return path, existing_name, class_def

            ratio = SequenceMatcher(None, target_norm, existing_norm).ratio()
            if ratio >= 0.92:
                if best is None or ratio > best[0]:
                    best = (ratio, path, existing_name, class_def)

    if best:
        return best[1], best[2], best[3]
    return None, None, None

def find_closest_class_candidate(yaml_files, class_name):
    """Return the closest existing class candidate (if any) for AI context."""
    target_norm = normalize_class_name(class_name)
    if not target_norm:
        return None

    best = None
    for path, data in yaml_files.items():
        if not data or "classes" not in data:
            continue
        for existing_name, class_def in data["classes"].items():
            existing_norm = normalize_class_name(existing_name)
            if not existing_norm:
                continue
            ratio = SequenceMatcher(None, target_norm, existing_norm).ratio()
            stem_ratio = SequenceMatcher(
                None, class_name_stem(class_name), class_name_stem(existing_name)
            ).ratio()
            score = max(ratio, stem_ratio)
            if best is None or score > best["score"]:
                best = {
                    "score": round(score, 4),
                    "class_name": existing_name,
                    "file": path,
                    "attribute_count": len(class_def.get("attributes", {}))
                    if isinstance(class_def, dict)
                    else 0,
                }
    return best

def build_class_catalog(yaml_files, modules_dir):
    """Build lightweight catalog of classes for AI context."""
    catalog = []
    modules_dir_abs = os.path.abspath(modules_dir)
    for path, data in yaml_files.items():
        if not data or "classes" not in data:
            continue
        rel_path = os.path.relpath(path, modules_dir_abs)
        for class_name, class_def in data["classes"].items():
            attrs = class_def.get("attributes") if isinstance(class_def, dict) else {}
            attr_count = len(attrs) if isinstance(attrs, dict) else 0
            catalog.append(
                {
                    "class_name": class_name,
                    "file": rel_path,
                    "attribute_count": attr_count,
                }
            )
    return catalog

def resolve_target_file(modules_dir, suggested_file, fallback_file):
    """Resolve suggested file path safely under modules_dir."""
    if not suggested_file:
        return fallback_file

    modules_abs = os.path.abspath(modules_dir)
    candidate = suggested_file.strip()
    if os.path.isabs(candidate):
        target = os.path.abspath(candidate)
    else:
        target = os.path.abspath(os.path.join(modules_abs, candidate))

    try:
        if os.path.commonpath([modules_abs, target]) != modules_abs:
            return fallback_file
    except ValueError:
        return fallback_file

    return target

def ai_review_class_placement(
    view_name,
    mapped_class_name,
    dd_fields,
    modules_dir,
    default_target_file,
    class_catalog,
    timeout,
    closest_candidate=None,
    ai_provider="gemini",
    use_codex_fallback=False,
    codex_timeout=60,
    user_feedback=None,
):
    """Ask AI where to place/create class for this view."""
    field_names = [f.get("field", "") for f in dd_fields[:20]]
    prompt = f"""You are helping place a clinical data model class in a LinkML repo.

View name: {view_name}
Mapped class name: {mapped_class_name}
Default target file: {os.path.relpath(default_target_file, os.path.abspath(modules_dir))}
Incoming fields (sample): {field_names}

Existing classes (sample):
{json.dumps(class_catalog[:60], indent=2)}

Closest class-matching candidate (if available):
{json.dumps(closest_candidate or {}, indent=2)}

Instructions:
- Prefer merging into an existing class when semantically compatible.
- Create a new class only when the incoming view is clearly distinct.
- If merged into an existing class, include merged source context in the reason. The script will append this merge source to the target class description.

Return ONLY JSON with this schema:
{{
  "action": "use_default" | "use_existing_class" | "create_new_class" | "rename_existing_class" | "skip",
  "source_class_name": "ExistingClassToRename (required only when action=rename_existing_class)",
  "class_name": "ClassName",
  "target_file": "clinical/assessments/example.yaml",
  "reason": "short reason"
}}
"""
    if user_feedback:
        prompt += f"\nUser feedback on previous suggestion:\n{user_feedback}\nPlease revise your suggestion accordingly.\n"

    parsed, source = run_ai_json(
        prompt,
        provider=ai_provider,
        timeout=timeout,
        use_codex_fallback=use_codex_fallback,
        codex_timeout=codex_timeout,
    )
    if not isinstance(parsed, dict):
        if use_codex_fallback:
            print("[AI Fallback] Gemini returned invalid/empty output and Codex fallback also failed.")
        # Prefer nearest known class when AI cannot provide a valid suggestion.
        if isinstance(closest_candidate, dict) and closest_candidate.get("class_name") and closest_candidate.get("file"):
            return {
                "action": "use_existing_class",
                "class_name": closest_candidate["class_name"],
                "target_file": closest_candidate["file"],
                "reason": "ai_unavailable_or_invalid_using_closest_match",
            }
        return {
            "action": "use_default",
            "class_name": mapped_class_name,
            "target_file": default_target_file,
            "reason": "ai_unavailable_or_invalid",
        }
    if source == "codex":
        print("[AI Fallback] Used Codex fallback for class placement suggestion.")

    action = parsed.get("action", "use_default")
    class_name = str(parsed.get("class_name", mapped_class_name)).strip() or mapped_class_name
    source_class_name = str(parsed.get("source_class_name", "")).strip()
    target_file = resolve_target_file(modules_dir, parsed.get("target_file"), default_target_file)
    reason = str(parsed.get("reason", "")).strip()
    return {
        "action": action,
        "source_class_name": source_class_name,
        "class_name": class_name,
        "target_file": target_file,
        "reason": reason,
    }

def ai_review_attribute_placement(
    view_name,
    class_name,
    target_file,
    attr_name,
    field,
    modules_dir,
    class_catalog,
    timeout,
    ai_provider="gemini",
    use_codex_fallback=False,
    codex_timeout=60,
    user_feedback=None,
):
    """Ask AI where to place a new attribute."""
    prompt = f"""You are helping place one new LinkML attribute.

View name: {view_name}
Default class: {class_name}
Default file: {os.path.relpath(target_file, os.path.abspath(modules_dir))}
Attribute name: {attr_name}
Field source info: {json.dumps(field, ensure_ascii=True)}

Existing classes (sample):
{json.dumps(class_catalog[:60], indent=2)}

Return ONLY JSON with this schema:
{{
  "action": "use_default" | "add_to_existing_class" | "skip",
  "class_name": "ClassName",
  "target_file": "clinical/assessments/example.yaml",
  "attribute_name": "camelCaseAttr",
  "range": "string",
  "title": "Human title",
  "reason": "short reason"
}}
"""
    if user_feedback:
        prompt += f"\nUser feedback on previous suggestion:\n{user_feedback}\nPlease revise your suggestion accordingly.\n"

    parsed, source = run_ai_json(
        prompt,
        provider=ai_provider,
        timeout=timeout,
        use_codex_fallback=use_codex_fallback,
        codex_timeout=codex_timeout,
    )
    if not isinstance(parsed, dict):
        if use_codex_fallback:
            print("[AI Fallback] Gemini returned invalid/empty output and Codex fallback also failed.")
        return {
            "action": "use_default",
            "class_name": class_name,
            "target_file": target_file,
            "attribute_name": attr_name,
            "range": "string",
            "title": field.get("description", ""),
            "reason": "ai_unavailable_or_invalid",
        }
    if source == "codex":
        print("[AI Fallback] Used Codex fallback for attribute placement suggestion.")

    action = parsed.get("action", "use_default")
    new_class = str(parsed.get("class_name", class_name)).strip() or class_name
    new_file = resolve_target_file(modules_dir, parsed.get("target_file"), target_file)
    new_attr = str(parsed.get("attribute_name", attr_name)).strip() or attr_name
    attr_range = str(parsed.get("range", "string")).strip() or "string"
    attr_title = str(parsed.get("title", field.get("description", ""))).strip() or field.get("description", "")
    reason = str(parsed.get("reason", "")).strip()
    return {
        "action": action,
        "class_name": new_class,
        "target_file": new_file,
        "attribute_name": new_attr,
        "range": attr_range,
        "title": attr_title,
        "reason": reason,
    }

# --- Main Logic ---

def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Update data model from data dictionaries.")
    parser.add_argument("--modules-dir", required=True, help="Path to the modules directory.")
    parser.add_argument("--dd-dir", help="Path to the root data dictionary directory (legacy local mode).")
    parser.add_argument("--assess-dd-synid", help="Synapse ID of ASSESS data dictionary CSV.")
    parser.add_argument("--prevent-dd-synid", help="Synapse ID of PREVENT data dictionary CSV.")
    parser.add_argument(
        "--dd-downloads-dir",
        default="downloads/data_dictionaries",
        help="Local directory for downloaded DD CSVs when using --assess-dd-synid/--prevent-dd-synid.",
    )
    parser.add_argument("--view-to-class", help="Path to an existing view_to_class_mapping.md file.")
    parser.add_argument(
        "--generate-view-to-class",
        action="store_true",
        help="Generate view_to_class_mapping.md from Synapse staging folders before updating model.",
    )
    parser.add_argument("--assess-staging-folder", help="Synapse folder ID for ASSESS staging CSVs.")
    parser.add_argument("--prevent-staging-folder", help="Synapse folder ID for PREVENT staging CSVs.")
    parser.add_argument(
        "--downloads-dir",
        default="downloads",
        help="Local downloads directory for staging CSVs (default: downloads).",
    )
    parser.add_argument(
        "--generated-view-to-class-path",
        default="view_to_class_mapping.md",
        help="Output path for generated markdown mapping (default: view_to_class_mapping.md).",
    )
    parser.add_argument(
        "--use-gemini-review",
        action="store_true",
        help="Use AI review to suggest class/attribute placement for each new addition and require user confirmation.",
    )
    parser.add_argument(
        "--ai-provider",
        choices=["gemini", "codex"],
        default="gemini",
        help="Primary AI provider for review mode (default: gemini). Set to codex to disable Gemini calls.",
    )
    parser.add_argument(
        "--gemini-timeout",
        type=int,
        default=60,
        help="Gemini timeout in seconds when --use-gemini-review is enabled and ai-provider=gemini (default: 60).",
    )
    parser.add_argument(
        "--use-codex-fallback",
        action="store_true",
        help="When ai-provider=gemini and Gemini fails to return valid JSON, fallback to Codex CLI.",
    )
    parser.add_argument(
        "--codex-timeout",
        type=int,
        default=60,
        help="Codex timeout in seconds for fallback AI calls (default: 60).",
    )
    parser.add_argument(
        "--auto-accept-gemini",
        action="store_true",
        help="When used with --use-gemini-review, automatically accept AI suggestions without per-change prompts.",
    )
    parser.add_argument(
        "--confirm-attribute-changes",
        action="store_true",
        help="When used with --use-gemini-review, require interactive confirmation for each attribute suggestion. "
             "By default, attribute suggestions are auto-accepted while class placement remains interactive.",
    )
    parser.add_argument("--dry-run", action="store_true", help="If set, the script will not write any files.")
    parser.add_argument(
        "--mode",
        choices=["assess", "apply"],
        default="apply",
        help="Processing mode: `assess` generates a proposal CSV, `apply` updates the model (default: apply).",
    )
    parser.add_argument(
        "--proposal-path",
        default="downloads/model_update_proposal.csv",
        help="Path to the proposal CSV written/consumed during assess/apply.",
    )
    parser.add_argument(
        "--checkpoint-path",
        default="checkpoints/update_model_from_dd_checkpoint.json",
        help="Path to the resume checkpoint file for pausing and resuming.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume processing from the last checkpoint.",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Discard existing checkpoint and restart processing for the given mode.",
    )
    parser.add_argument(
        "--pause-after",
        type=int,
        default=0,
        help="Pause after N processed items (assess/apply) and checkpoint progress.",
    )
    parser.add_argument(
        "--enum-strategy",
        choices=["reuse-first", "always-new", "keep-string"],
        default="reuse-first",
        help="Enum handling when listing DD values (default: reuse-first).",
    )
    parser.add_argument(
        "--boolean-rule",
        choices=["strict", "normalize", "none"],
        default="strict",
        help="Boolean normalization rule for DD values (default: strict true/false only).",
    )
    
    args = parser.parse_args()
    if args.generate_view_to_class:
        if not args.assess_staging_folder or not args.prevent_staging_folder:
            parser.error(
                "--generate-view-to-class requires both --assess-staging-folder and --prevent-staging-folder."
            )

    if not args.generate_view_to_class and not args.view_to_class:
        parser.error(
            "Either provide --view-to-class or use --generate-view-to-class."
        )
    if (args.assess_dd_synid and not args.prevent_dd_synid) or (args.prevent_dd_synid and not args.assess_dd_synid):
        parser.error(
            "Provide both --assess-dd-synid and --prevent-dd-synid together."
        )
    if not args.dd_dir and not (args.assess_dd_synid and args.prevent_dd_synid):
        parser.error(
            "Provide data dictionaries via --dd-dir or both --assess-dd-synid and --prevent-dd-synid."
        )
    if args.use_codex_fallback and not check_codex_available():
        parser.error(
            "--use-codex-fallback requested but codex CLI is not available."
        )
    if args.auto_accept_gemini and not args.use_gemini_review:
        parser.error(
            "--auto-accept-gemini requires --use-gemini-review."
        )

    if args.use_gemini_review:
        if args.ai_provider == "gemini":
            if not check_gemini_available():
                if not check_codex_available():
                    parser.error(
                        "--use-gemini-review with ai-provider=gemini requires gemini CLI, "
                        "or codex CLI for fallback."
                    )
            effective_use_codex_fallback = bool(args.use_codex_fallback)
        else:
            # codex primary mode: no Gemini calls.
            if not check_codex_available():
                parser.error(
                    "--use-gemini-review with ai-provider=codex requires codex CLI."
                )
            effective_use_codex_fallback = False
    else:
        effective_use_codex_fallback = False

    if args.pause_after < 0:
        parser.error("--pause-after must be zero or positive.")

    checkpoint_path = os.path.abspath(args.checkpoint_path)
    if args.reset_checkpoint and os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
    checkpoint_root = load_checkpoint(checkpoint_path) or {}
    modes_state = checkpoint_root.setdefault("modes", {})
    if args.reset_checkpoint:
        modes_state.pop(args.mode, None)
    mode_checkpoint = modes_state.setdefault(args.mode, {})
    args_signature = compute_args_signature(args, args.proposal_path)
    if mode_checkpoint.get("args_signature") and mode_checkpoint["args_signature"] != args_signature:
        parser.error("Checkpoint arguments differ; run with --reset-checkpoint to continue.")

    signal.signal(signal.SIGINT, _signal_handler)

    # --- Load Data ---
    print("Loading data...")
    view_to_class_path = args.view_to_class
    if args.generate_view_to_class:
        generated_path = generate_view_to_class_mapping_from_synapse(
            assess_folder_id=args.assess_staging_folder,
            prevent_folder_id=args.prevent_staging_folder,
            downloads_dir=args.downloads_dir,
            output_path=args.generated_view_to_class_path,
        )
        if not view_to_class_path:
            view_to_class_path = generated_path

    view_to_class = parse_view_to_class_mapping(view_to_class_path)
    view_to_form_name = parse_view_to_form_name_mapping(view_to_class_path)
    
    dd_paths = resolve_data_dictionary_paths(args)
    all_dd_data = {}
    for dataset in ["ASSESS", "PREVENT"]:
        dd_path = dd_paths.get(dataset)
        if not dd_path:
            print(f"Warning: No DD path resolved for {dataset}. Skipping.", file=sys.stderr)
            continue
        all_dd_data.update(parse_data_dictionary(dd_path))

    yaml_files = load_yaml_files(args.modules_dir)
    
    # --- Process Data ---
    print("Processing data model updates...")
    class_catalog = build_class_catalog(yaml_files, args.modules_dir)
    if args.mode == "assess":
        run_assess_mode(
            args=args,
            view_to_class=view_to_class,
            view_to_form_name=view_to_form_name,
            all_dd_data=all_dd_data,
            yaml_files=yaml_files,
            checkpoint_root=checkpoint_root,
            mode_checkpoint=mode_checkpoint,
            args_signature=args_signature,
        )
        return
    enum_catalog = build_enum_catalog(yaml_files)
    existing_enum_names = {entry["name"] for entry in enum_catalog}
    for view_name, dd_fields in all_dd_data.items():
        if stop_requested:
            break
        normalized_view_name = normalize_view_name(view_name)
        if normalized_view_name not in view_to_class:
            print(f"Warning: View '{view_name}' not found in mapping file. Skipping.", file=sys.stderr)
            continue
            
        mapped_class_name = view_to_class[normalized_view_name]
        mapped_form_name = view_to_form_name.get(normalized_view_name, "")

        found_path, found_class_name, found_class_def = find_class_in_yaml(yaml_files, mapped_class_name, loose=False)
        default_class_name = mapped_class_name
        if found_path:
            default_target_file = found_path
        else:
            # AI-first placement mode: when AI review is enabled, let Gemini/Codex choose the
            # target file from existing assessment files. Use a neutral fallback only if AI fails.
            if args.use_gemini_review:
                default_target_file = os.path.join(
                    args.modules_dir, "clinical", "assessments", "other_generated_assessments.yaml"
                )
                print(
                    f"  [Placement] AI-first placement for new class '{mapped_class_name}' "
                    f"(fallback file: {default_target_file})"
                )
            else:
                default_target_file = choose_grouped_assessment_file(args.modules_dir, yaml_files, mapped_class_name)
                print(f"  [Placement] Heuristic target for new class '{mapped_class_name}': {default_target_file}")

        closest_candidate = find_closest_class_candidate(yaml_files, mapped_class_name) if not found_path else None
        if closest_candidate:
            print(
                f"  [Class match] Closest candidate for '{mapped_class_name}': "
                f"{closest_candidate['class_name']} (score={closest_candidate['score']}, file={closest_candidate['file']})"
            )

        # Optional AI review for class placement (new additions only).
        class_name = default_class_name
        target_file = default_target_file
        force_create_new_class = False
        rename_source_class_name = ""
        if found_path:
            class_name = found_class_name
        elif args.use_gemini_review:
            class_decision = ai_review_class_placement(
                view_name=view_name,
                mapped_class_name=mapped_class_name,
                dd_fields=dd_fields,
                modules_dir=args.modules_dir,
                default_target_file=default_target_file,
                class_catalog=class_catalog,
                timeout=args.gemini_timeout,
                closest_candidate=closest_candidate,
                ai_provider=args.ai_provider,
                use_codex_fallback=effective_use_codex_fallback,
                codex_timeout=args.codex_timeout,
            )
            if args.auto_accept_gemini:
                print(
                    f"[AI:{args.ai_provider}][auto-accept] Class suggestion for {view_name}: action={class_decision['action']} "
                    f"source_class={class_decision.get('source_class_name', '')} "
                    f"class={class_decision['class_name']} file={class_decision['target_file']} "
                    f"reason={class_decision.get('reason', '')}"
                )
                if class_decision.get("action") == "skip":
                    print(f"  Skipping view '{view_name}' by AI suggestion.")
                    continue
                class_name = class_decision.get("class_name", default_class_name)
                target_file = class_decision.get("target_file", default_target_file)
                force_create_new_class = class_decision.get("action") == "create_new_class"
                if class_decision.get("action") == "rename_existing_class":
                    rename_source_class_name = class_decision.get("source_class_name", "")
            else:
                while True:
                    print(
                        f"[AI:{args.ai_provider}] Class suggestion for {view_name}: action={class_decision['action']} "
                        f"source_class={class_decision.get('source_class_name', '')} "
                        f"class={class_decision['class_name']} file={class_decision['target_file']} "
                        f"reason={class_decision.get('reason', '')}"
                    )
                    review_action = prompt_review_action(
                        f"Review class decision for view {view_name}"
                    )
                    if review_action == "accept":
                        if class_decision.get("action") == "skip":
                            print(f"  Skipping view '{view_name}' by AI suggestion.")
                            class_name = None
                            break
                        class_name = class_decision.get("class_name", default_class_name)
                        target_file = class_decision.get("target_file", default_target_file)
                        force_create_new_class = class_decision.get("action") == "create_new_class"
                        if class_decision.get("action") == "rename_existing_class":
                            rename_source_class_name = class_decision.get("source_class_name", "")
                        else:
                            rename_source_class_name = ""
                        break
                    if review_action == "skip":
                        print(f"  Skipping view '{view_name}' by user decision.")
                        class_name = None
                        break

                    feedback = input("Enter feedback for AI class suggestion: ").strip()
                    class_decision = ai_review_class_placement(
                        view_name=view_name,
                        mapped_class_name=mapped_class_name,
                        dd_fields=dd_fields,
                        modules_dir=args.modules_dir,
                        default_target_file=default_target_file,
                        class_catalog=class_catalog,
                        timeout=args.gemini_timeout,
                        closest_candidate=closest_candidate,
                        ai_provider=args.ai_provider,
                        use_codex_fallback=effective_use_codex_fallback,
                        codex_timeout=args.codex_timeout,
                        user_feedback=feedback,
                    )

                if not class_name:
                    continue
        elif closest_candidate and closest_candidate["score"] >= 0.92:
            class_name = closest_candidate["class_name"]
            target_file = closest_candidate["file"]
            print(
                f"  [Loose match] Reusing existing class '{class_name}' "
                f"for mapped class '{mapped_class_name}'"
            )

        if rename_source_class_name:
            renamed, renamed_path, renamed_class_def, touched_paths, rename_message = rename_class_and_references(
                yaml_files=yaml_files,
                old_class_name=rename_source_class_name,
                new_class_name=class_name,
            )
            if renamed:
                print(
                    f"  [Rename] Renamed existing class '{rename_source_class_name}' to '{class_name}' "
                    f"in '{renamed_path}'."
                )
                add_merge_note_to_class_description(
                    class_def=renamed_class_def,
                    mapped_class_name=mapped_class_name,
                    view_name=view_name,
                    form_name=mapped_form_name,
                )
                for touched_path in touched_paths:
                    persist_yaml_file(touched_path, yaml_files[touched_path], args.dry_run)
                class_catalog = build_class_catalog(yaml_files, args.modules_dir)
            else:
                print(
                    f"  [Rename] Could not rename '{rename_source_class_name}' to '{class_name}': {rename_message}. "
                    "Continuing without rename."
                )

        # Re-check whether class exists (class name may have changed after AI decision)
        found_path, found_class_name, found_class_def = find_class_in_yaml(
            yaml_files, class_name, loose=(not force_create_new_class)
        )
        if found_path:
            target_file = found_path
            class_name = found_class_name
            class_def = found_class_def
            if normalize_class_name(class_name) != normalize_class_name(mapped_class_name):
                add_merge_note_to_class_description(
                    class_def=class_def,
                    mapped_class_name=mapped_class_name,
                    view_name=view_name,
                    form_name=mapped_form_name,
                )
                persist_yaml_file(target_file, yaml_files[target_file], args.dry_run)
        else:
            print(f"Creating new class '{class_name}' in file '{target_file}'")
            if target_file not in yaml_files or not yaml_files.get(target_file):
                yaml_files[target_file] = {}
            if "classes" not in yaml_files[target_file] or yaml_files[target_file]["classes"] is None:
                yaml_files[target_file]["classes"] = {}
            yaml_files[target_file]["classes"][class_name] = {
                "is_a": "ClinicalAssessment",
                "description": infer_class_description(view_name, mapped_form_name),
                "attributes": {},
            }
            class_def = yaml_files[target_file]["classes"][class_name]
            # Refresh class catalog for downstream AI context
            class_catalog = build_class_catalog(yaml_files, args.modules_dir)
            persist_yaml_file(target_file, yaml_files[target_file], args.dry_run)

        if "attributes" not in class_def or class_def["attributes"] is None:
            class_def["attributes"] = {}

        for field in dd_fields:
            if stop_requested:
                break
            attr_name = to_camel_case(field['field'])
            if not attr_name:
                continue

            # Skip if already present in the current class.
            if attr_name in class_def["attributes"]:
                continue

            target_class_name = class_name
            target_file_for_attr = target_file
            target_attr_name = attr_name
            target_attr_range = "string"
            target_attr_title = field.get("description", "")

            if args.use_gemini_review:
                attr_decision = ai_review_attribute_placement(
                    view_name=view_name,
                    class_name=class_name,
                    target_file=target_file,
                    attr_name=attr_name,
                    field=field,
                    modules_dir=args.modules_dir,
                    class_catalog=class_catalog,
                    timeout=args.gemini_timeout,
                    ai_provider=args.ai_provider,
                    use_codex_fallback=effective_use_codex_fallback,
                    codex_timeout=args.codex_timeout,
                )
                field_raw_name = field.get("field", "")
                force_attribute_confirmation = is_view_like_name(field_raw_name)
                if force_attribute_confirmation:
                    print(
                        f"[Guard] Field '{field_raw_name}' looks like a view name; "
                        "forcing interactive review before adding as attribute."
                    )

                if args.auto_accept_gemini and not force_attribute_confirmation:
                    print(
                        f"[AI:{args.ai_provider}][auto-accept-attr] Attribute suggestion: action={attr_decision['action']} "
                        f"class={attr_decision['class_name']} file={attr_decision['target_file']} "
                        f"attr={attr_decision['attribute_name']} range={attr_decision['range']} "
                        f"reason={attr_decision.get('reason', '')}"
                    )
                    if attr_decision.get("action") == "skip":
                        print(f"  Skipped attribute '{attr_name}' by AI suggestion.")
                        target_class_name = None
                    else:
                        target_class_name = attr_decision.get("class_name", class_name)
                        target_file_for_attr = attr_decision.get("target_file", target_file)
                        target_attr_name = attr_decision.get("attribute_name", attr_name)
                        target_attr_range = attr_decision.get("range", "string") or "string"
                        target_attr_title = attr_decision.get("title", field.get("description", "")) or field.get("description", "")
                elif (not args.confirm_attribute_changes) and not force_attribute_confirmation:
                    print(
                        f"[AI:{args.ai_provider}][auto-accept-attr] Attribute suggestion: action={attr_decision['action']} "
                        f"class={attr_decision['class_name']} file={attr_decision['target_file']} "
                        f"attr={attr_decision['attribute_name']} range={attr_decision['range']} "
                        f"reason={attr_decision.get('reason', '')}"
                    )
                    if attr_decision.get("action") == "skip":
                        print(f"  Skipped attribute '{attr_name}' by AI suggestion.")
                        target_class_name = None
                    else:
                        target_class_name = attr_decision.get("class_name", class_name)
                        target_file_for_attr = attr_decision.get("target_file", target_file)
                        target_attr_name = attr_decision.get("attribute_name", attr_name)
                        target_attr_range = attr_decision.get("range", "string") or "string"
                        target_attr_title = attr_decision.get("title", field.get("description", "")) or field.get("description", "")
                else:
                    while True:
                        print(
                            f"[AI:{args.ai_provider}] Attribute suggestion: action={attr_decision['action']} "
                            f"class={attr_decision['class_name']} file={attr_decision['target_file']} "
                            f"attr={attr_decision['attribute_name']} range={attr_decision['range']} "
                            f"reason={attr_decision.get('reason', '')}"
                        )
                        review_action = prompt_review_action(
                            f"Review attribute decision for field '{field['field']}' in view '{view_name}'"
                        )
                        if review_action == "accept":
                            if attr_decision.get("action") == "skip":
                                print(f"  Skipped attribute '{attr_name}' by AI suggestion.")
                                target_class_name = None
                            else:
                                target_class_name = attr_decision.get("class_name", class_name)
                                target_file_for_attr = attr_decision.get("target_file", target_file)
                                target_attr_name = attr_decision.get("attribute_name", attr_name)
                                target_attr_range = attr_decision.get("range", "string") or "string"
                                target_attr_title = attr_decision.get("title", field.get("description", "")) or field.get("description", "")
                            break
                        if review_action == "skip":
                            print(f"  Skipped attribute '{attr_name}' by user decision.")
                            target_class_name = None
                            break

                        feedback = input("Enter feedback for AI attribute suggestion: ").strip()
                        attr_decision = ai_review_attribute_placement(
                            view_name=view_name,
                            class_name=class_name,
                            target_file=target_file,
                            attr_name=attr_name,
                            field=field,
                            modules_dir=args.modules_dir,
                            class_catalog=class_catalog,
                            timeout=args.gemini_timeout,
                            ai_provider=args.ai_provider,
                            use_codex_fallback=effective_use_codex_fallback,
                            codex_timeout=args.codex_timeout,
                            user_feedback=feedback,
                        )

            if not target_class_name:
                continue

            item_key = compute_item_key(view_name, target_attr_name, target_class_name)
            if item_key in completed_keys:
                continue

            # Ensure target class exists for attribute placement.
            target_path_existing, target_class_existing_name, target_class_def = find_class_in_yaml(
                yaml_files, target_class_name, loose=True
            )
            if target_path_existing:
                target_file_for_attr = target_path_existing
                target_class_name = target_class_existing_name
            else:
                print(f"  Creating target class '{target_class_name}' in '{target_file_for_attr}' for attribute placement")
                if target_file_for_attr not in yaml_files or not yaml_files.get(target_file_for_attr):
                    yaml_files[target_file_for_attr] = {}
                if "classes" not in yaml_files[target_file_for_attr] or yaml_files[target_file_for_attr]["classes"] is None:
                    yaml_files[target_file_for_attr]["classes"] = {}
                yaml_files[target_file_for_attr]["classes"][target_class_name] = {
                    "is_a": "ClinicalAssessment",
                    "description": infer_class_description(view_name, mapped_form_name),
                    "attributes": {},
                }
                target_class_def = yaml_files[target_file_for_attr]["classes"][target_class_name]
                class_catalog = build_class_catalog(yaml_files, args.modules_dir)
                persist_yaml_file(target_file_for_attr, yaml_files[target_file_for_attr], args.dry_run)

            if "attributes" not in target_class_def or target_class_def["attributes"] is None:
                target_class_def["attributes"] = {}

            if target_attr_name in target_class_def["attributes"]:
                print(f"  Attribute '{target_attr_name}' already exists in class '{target_class_name}'. Skipping.")
                completed_keys.add(item_key)
                processed_count += 1
                pause_counter += 1
                persist_checkpoint_state()
                continue

            target_attr_range, enum_action, enum_entry = determine_attribute_range(
                args,
                field,
                target_attr_range,
                target_class_name,
                target_file_for_attr,
                yaml_files,
                enum_catalog,
                existing_enum_names,
            )
            print(f"  Adding attribute '{target_attr_name}' to class '{target_class_name}'")
            target_class_def["attributes"][target_attr_name] = {
                "title": target_attr_title,
                "description": field.get("description", ""),
                "range": target_attr_range,
            }
            persist_yaml_file(target_file_for_attr, yaml_files[target_file_for_attr], args.dry_run)
            if enum_action == "create" and enum_entry:
                print(
                    f"    [Enum] Created '{enum_entry['name']}' in {enum_entry['file']} "
                    f"with {len(enum_entry['raw_values'])} values."
                )
            if enum_action == "reuse" and enum_entry:
                print(
                    f"    [Enum] Reusing '{enum_entry['name']}' from {enum_entry['file']}."
                )
            completed_keys.add(item_key)
            processed_count += 1
            pause_counter += 1
            persist_checkpoint_state()
            if args.pause_after and pause_counter >= args.pause_after:
                print(f"  [Apply] pause triggered after {pause_counter} processed items.")
                stop_requested = True
                break

    if stop_requested:
        print(f"[Apply] Processing paused after {pause_counter} items. Run with --resume.")

    persist_checkpoint_state()

    # --- Write Changes ---
    if not args.dry_run:
        print("Writing changes to YAML files...")
        yaml = YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        for path, data in yaml_files.items():
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    yaml.dump(data, f)
            except Exception as e:
                print(f"Error writing to {path}: {e}", file=sys.stderr)
    else:
        print("Dry run complete. No files were written.")


if __name__ == "__main__":
    main()

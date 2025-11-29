# -*- coding: utf-8 -*-
__author__ = 'wchen (modified by ifrankel)'

import sys
import os
import yaml
from lxml import etree
import csv
import argparse
import multiprocessing
import re

def process_file(file_path, config, destdir):
    """
    Processes a single XML file:
      - Strips namespaces
      - Processes teiHeader for metadata
      - Processes text for output
      - Preserves paragraph/newline breaks from YAML config
    """
    filename = os.path.basename(file_path)
    csv_dict = {'Filename': filename}

    try:
        # Parse XML
        parser = etree.XMLParser(remove_blank_text=True, ns_clean=True, recover=True)
        tree = etree.parse(file_path, parser)
        treeroot = tree.getroot()

        # --- Strip namespaces ---
        for elem in treeroot.iter():
            if not hasattr(elem.tag, 'find'):
                continue
            i = elem.tag.find('}')
            if i != -1:
                elem.tag = elem.tag[i + 1:]

    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return None

    def node_process(node):
        """
        Recursively process XML nodes according to YAML config,
        updating csv_dict and returning text with preserved paragraph breaks.
        """
        if node is None:
            return ""

        buffer = []
        if node.text:
            buffer.append(node.text)

        for child in node:
            buffer.append(node_process(child))
            if child.tail:
                buffer.append(child.tail)

        full_text = ''.join(filter(None, buffer))

        # YAML tag matching
        tag_upper = node.tag.upper()
        node_config = config.get(tag_upper, {})
        main_config = node_config.get('main-config', [])
        if main_config is None:
            main_config = []

        if 'ignore' in main_config:
            return ""

        if "csv" in main_config:
            if tag_upper == 'DATE':
                path_str = tree.getelementpath(node).upper()
                if 'SOURCEDESC' in path_str:
                    csv_dict['SRC-DATE'] = node.text
                elif 'FILEDESC' in path_str:
                    csv_dict['DATE'] = node.text
            else:
                csv_dict[tag_upper] = node.text

        # Add line breaks based on config
        if "newLine" in main_config:
            full_text = full_text.rstrip() + '\n'
        elif 'doubleNewLine' in main_config:
            full_text = full_text.rstrip() + '\n\n'

        return full_text

    # --- Process teiHeader for metadata ---
    header_node = treeroot.find('./teiHeader')
    if header_node is not None:
        node_process(header_node)

    # --- Process main text for output ---
    text_node = treeroot.find('./text')
    if text_node is not None:
        str_to_write = node_process(text_node)
    else:
        print(f"Warning: <text> tag not found in {filename}. Including whole file.", file=sys.stderr)
        str_to_write = node_process(treeroot)

    # --- Clean spacing while preserving intentional newlines ---
    # Collapse multiple spaces/tabs into one, but keep \n intact
    str_to_write = re.sub(r'[ \t]+', ' ', str_to_write)
    # Normalize multiple blank lines to max two
    str_to_write = re.sub(r'\n\s*\n', '\n\n', str_to_write).strip()

    # Save .txt
    output_file = os.path.splitext(filename)[0] + '.txt'
    with open(os.path.join(destdir, output_file), 'w', encoding='ascii', errors='ignore') as f:
        f.write(str_to_write)

    # Metadata: pages & wordcount
    pages = len(treeroot.findall('.//pb'))
    wordcount = len(str_to_write.split())
    csv_dict['Pages'] = pages
    csv_dict['WordCount'] = wordcount

    # Metadata from attributes
    for node in treeroot.iter():
        tag_upper = node.tag.upper()
        node_config = config.get(tag_upper, {})
        for att, att_config in node_config.items():
            if att != 'main-config' and att_config and "csv" in att_config:
                if att in node.attrib:
                    csv_dict[f"{tag_upper}.{att}"] = node.attrib[att]

    return csv_dict


def main():
    parser = argparse.ArgumentParser(description='TEI Decoder - extracts plain-text from annotated xml')
    parser.add_argument('yaml_config', help='Path to the uppercase config.yaml file')
    parser.add_argument('input_path', help='Path to a directory of XML files')
    parser.add_argument('output_path', help='Path to the output folder')
    args = parser.parse_args()

    if not os.path.exists(args.output_path):
        os.makedirs(args.output_path)
    if not os.path.exists(args.input_path):
        print(f"Error: Source path '{args.input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(args.yaml_config, 'r') as stream:
        config = yaml.safe_load(stream)

    xml_files = [os.path.join(dp, f) for dp, _, fn in os.walk(args.input_path) for f in fn if f.lower().endswith('.xml')]
    print(f"Found {len(xml_files)} XML files to process.")

    with multiprocessing.Pool() as pool:
        results = pool.starmap(process_file, [(file_path, config, args.output_path) for file_path in xml_files])

    results = [res for res in results if res]
    if not results:
        print("No XML files were successfully processed.")
        return

    all_keys = set().union(*(d.keys() for d in results))
    preferred_order = ['Filename', 'TITLE', 'AUTHOR', 'DATE', 'SRC-DATE', 'Pages', 'WordCount']
    final_fieldnames = sorted(list(all_keys), key=lambda x: (preferred_order.index(x) if x in preferred_order else len(preferred_order), x.upper()))

    with open(os.path.join(args.output_path, "meta.csv"), 'w', encoding='utf-8', newline='') as csvfile:
        csvwriter = csv.DictWriter(csvfile, fieldnames=final_fieldnames)
        csvwriter.writeheader()
        csvwriter.writerows(results)
    
    print(f"\nProcessing complete. {len(results)} files were processed and saved to '{args.output_path}'.")

if __name__ == '__main__':
    main()
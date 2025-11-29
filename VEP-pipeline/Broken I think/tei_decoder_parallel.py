# -*- coding: utf-8 -*-
__author__ = 'wchen'

import sys
import os
import yaml
from lxml import etree
import codecs
import csv
import argparse
import multiprocessing

def process_file(file_path, config, destdir):
    """
    Processes a single XML file, extracts text and metadata.

    Args:
        file_path (str): The full path to the XML file.
        config (dict): The configuration dictionary loaded from the YAML file.
        destdir (str): The destination directory for the output text file.

    Returns:
        dict: A dictionary containing the metadata for the processed file.
    """
    filename = os.path.basename(file_path)
    csv_dict = {'Filename': filename}

    try:
        # --- KEY CHANGE HERE: Create a parser to strip namespaces ---
        # This will remove the "xmlns" part from tags, allowing them to match the config file.
        parser = etree.XMLParser(remove_blank_text=True, ns_clean=True, recover=True)
        tree = etree.parse(file_path, parser)
        treeroot = tree.getroot()
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


    def node_process(node, ignore):
        visited_child = []
        out_buf = ''
        
        # Use .get() for safer dictionary access
        node_config = config.get(node.tag, {})
        main_config = node_config.get('main-config', {})

        if main_config:
            if "csv" in main_config:
                if node.tag == 'DATE': # special case
                    dist_path = str(tree.getelementpath(node))
                    if 'CHANGE' in dist_path:
                        pass
                    elif 'SOURCEDESC' in dist_path:
                        csv_dict['SRC-DATE'] = node.text
                    elif 'FILEDESC' in dist_path:
                        csv_dict['DATE'] = node.text
                else:
                    csv_dict[node.tag] = node.text
            if "tag" in main_config:
                out_buf += f"<{node.tag}"
                k = list(node.attrib.keys())
                for i, key in enumerate(k):
                    out_buf += f' {key}="{node.attrib[key]}"'
                out_buf += '>'

            if "text" in main_config:
                if node.text is not None:
                    out_buf += (node.text).replace('\n',' ')

            if 'ignore' in main_config:
                ignore = True

        # add the attributes into metadata
        for att, att_config in node_config.items():
            if att != 'main-config':
                if att_config and "csv" in att_config: # an attribute
                    if f"{node.tag}.{att}" not in csv_dict: # prevent from that key already exists
                        if att in node.attrib:
                            csv_dict[f"{node.tag}.{att}"] = node.attrib[att]
        """
        Start to append all its child content (tag ,text)
        """
        for child in node:
            if child is node:
                continue
            visited_child.append(child)
            # call recursive()
            child_visited_list, child_out_buf = node_process(child, ignore)
            out_buf += ' ' + child_out_buf
            for ch in child_visited_list:
                visited_child.append(ch)

        if main_config:
            if "tag" in main_config:
                out_buf += f"</{node.tag}>"

            if "newLine" in main_config:
                out_buf += '\n'
            elif 'doubleNewLine' in main_config:
                out_buf += '\n\n'

            parent = node.getparent()
            parent_config = config.get(parent.tag, {}) if parent is not None else {}
            if parent_config.get('main-config'):
                if node.tail is not None:
                    out_buf += (node.tail).replace('\n',' ')
            if ignore is True:
                out_buf = ''
        return visited_child, out_buf


    str_to_write = u''
    # recursively processing XML node
    visited_list, out_buf = node_process(treeroot, False)
    str_to_write += ' ' + out_buf

    #fixes VARD bugs caused by words adjacent to --

    if '--' in str_to_write:
        str_to_write = str_to_write.replace('--', ' -- ')

    while '  ' in str_to_write:
        str_to_write = str_to_write.replace('  ', ' ')
    # punctuation adjustment
    while ' ,' in str_to_write:
        str_to_write = str_to_write.replace(' ,', ',')
    while ' .' in str_to_write:
        str_to_write = str_to_write.replace(' .', '.')
    while ' )' in str_to_write:
        str_to_write = str_to_write.replace(' )', ')')
    while ' :' in str_to_write:
        str_to_write = str_to_write.replace(' :', ':')
    while ' ;' in str_to_write:
        str_to_write = str_to_write.replace(' ;', ';')
    while ' ?' in str_to_write:
        str_to_write = str_to_write.replace(' ?', '?')
    while ' !' in str_to_write:
        str_to_write = str_to_write.replace(' !', '!')
    while '  --  ' in str_to_write:
        str_to_write = str_to_write.replace('  --  ', ' -- ')


    # arrange the document to fit an 80 character limit per line
    buf = str_to_write
    str_to_write = ''
    line_len = 80
    for line in buf.split('\n'):
        line = line.strip()
        if len(line) > line_len:
            i = 0
            while i < len(line):
                if i + line_len >= len(line):
                    str_to_write += line[i:] + '\n'
                    break
                
                indice_lastspace = line.rfind(' ', i, i + line_len)
                if indice_lastspace == -1 or indice_lastspace <= i:
                    indice_lastspace = i + line_len

                str_to_write += line[i:indice_lastspace].strip() + '\n'
                i = indice_lastspace + 1
        else:
            str_to_write += line + '\n'

    output_file = filename.replace(os.path.splitext(filename)[1], '.txt')
    with open(os.path.join(destdir, output_file), mode='w',encoding='ascii', errors='ignore') as f:
        f.write(str_to_write)
    
    # XPath also needs to be namespace-free, which our parser now handles
    pages = len(treeroot.findall('.//pb')) # Use lowercase for tag names
    wordcount = len(str_to_write.split())
    csv_dict['Pages'] = pages
    csv_dict['WordCount'] = wordcount

    return csv_dict


def main():
    parser = argparse.ArgumentParser(description='TEI Decoder - extracts plain-text from annotated xml')
    parser.add_argument('yaml_config', help='path to config.yaml file - we recommend config_all_TCP for TCP files')
    parser.add_argument('input_path', help='path to directory of xml files relative to the location of this script')
    parser.add_argument('output_path', help='path to output folder relative to the location of this script')

    args = parser.parse_args()

    config_file = args.yaml_config
    rootdir = args.input_path
    destdir = args.output_path


    if not os.path.exists(destdir):
        os.makedirs(destdir)

    if not os.path.exists(rootdir):
        print(f"Error: unable to open source path {rootdir}")
        sys.exit(1)

    # Use yaml.safe_load for security
    with open(config_file, 'r') as stream:
        config = yaml.safe_load(stream)

    xml_files = []
    for dirpath, subdirs, files in os.walk(rootdir):
        for filename in files:
            if filename.lower().endswith(".xml"):
                xml_files.append(os.path.join(dirpath, filename))

    # Use all available cores
    with multiprocessing.Pool() as pool:
        results = pool.starmap(process_file, [(file_path, config, destdir) for file_path in xml_files])

    # Filter out None results from failed file processing
    results = [res for res in results if res]

    if not results:
        print("No XML files were successfully processed.")
        return

    # Dynamically generate fieldnames from all results to ensure no data is lost
    all_keys = set()
    for res in results:
        all_keys.update(res.keys())
    
    # Define a preferred order for common fields
    preferred_order = ['Filename', 'title', 'author', 'DATE', 'SRC-DATE', 'Pages', 'WordCount']
    
    # Create the final fieldname list
    final_fieldnames = sorted(list(all_keys), key=lambda x: (preferred_order.index(x) if x in preferred_order else len(preferred_order), x))


    with codecs.open(os.path.join(destdir, "meta.csv"), mode='w', encoding='utf-8') as csvfile:
        csvwriter = csv.DictWriter(csvfile, fieldnames=final_fieldnames)
        csvwriter.writeheader()
        csvwriter.writerows(results)
    
    print(f"\nProcessing complete. {len(results)} files were processed and saved to '{destdir}'.")


if __name__ == '__main__':
    main()
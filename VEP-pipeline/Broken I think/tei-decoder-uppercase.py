# -*- coding: utf-8 -*-
__author__ = 'wchen'

import sys
import os
import yaml
from lxml import etree
import codecs
import csv
import argparse

parser = argparse.ArgumentParser(description='TEI Decoder - extracts plain-text from annotated xml')
parser.add_argument('yaml_config', help='path to config.yaml file - we recommend config_all_TCP for TCP files')
parser.add_argument('input_path', help='path to directory of xml files relative to the location of this script')
parser.add_argument('output_path', help='path to output folder relative to the location of this script')

def strip_ns(tag):
    """Strip namespace from XML tag."""
    return tag.split('}', 1)[-1] if '}' in tag else tag


args = parser.parse_args()

config_file = args.yaml_config
rootdir = args.input_path
destdir = args.output_path


if not os.path.exists(destdir):
    os.makedirs(destdir)

if not os.path.exists(rootdir):
    print("Error: unable to open source path",rootdir)

stream = open(config_file, 'rb')
config = yaml.load(stream)
csvfile = codecs.open(destdir+"/meta.csv", mode='wb', encoding='utf-8')
fieldnames = []
csv_dict = {}
fieldnames.append('Filename')
for key in config:
    for att in config[key].keys():
        if (config[key][att] is not None) and ("csv" in config[key][att]):
            if att == 'main-config':
                fieldnames.append(key)
            else:
                fieldnames.append(key+'.'+att)
fieldnames.append('SRC-DATE')
fieldnames.append('Pages')
fieldnames.append('WordCount')
csvwriter = csv.DictWriter(csvfile, fieldnames=fieldnames)
csvwriter.writeheader()

def node_process(node, ignore):

    visited_child = []
    out_buf = ''

    tag = strip_ns(node.tag)
    print(f"Processing tag: {tag}, ignore={ignore}")
    print("csv_dict keys:", list(csv_dict.keys()))

    if tag not in config:
        # Skip this tag’s own processing but **process children**
        for child in node:
            v, b = node_process(child, ignore)
            visited_child.extend(v)
            out_buf += b
        return visited_child, out_buf

    # If we get here, tag is in config — process as before
    if config[tag]['main-config'] is not None:
        if "csv" in config[tag]['main-config']:
            if tag == 'DATE':  # special case
                dist_path = str(tree.getelementpath(node))
                if 'CHANGE' in dist_path:
                    pass
                elif 'SOURCEDESC' in dist_path:
                    csv_dict['SRC-DATE'] = node.text
                elif 'FILEDESC' in dist_path:
                    csv_dict['DATE'] = node.text
            else:
                csv_dict[node.tag] = node.text
        if "tag" in config[tag]['main-config']:
            out_buf += "<" + node.tag
            k = list(node.attrib.keys())
            for i in range(len(k)):
                if i == 0:
                    out_buf += ' '
                if i != len(k) - 1:
                    out_buf += f'{k[i]}="{node.attrib[k[i]]}" '
                else:
                    out_buf += f'{k[i]}="{node.attrib[k[i]]}"'
            out_buf += '>'

        if "text" in config[tag]['main-config']:
            if node.text is not None:
                out_buf += node.text.replace('\n', ' ')

        if 'ignore' in config[tag]['main-config']:
            ignore = True

    # Add attributes to metadata
    for att in config[tag].keys():
        if att != 'main-config':
            if config[tag][att] is not None and "csv" in config[tag][att]:
                key = node.tag + '.' + att
                if key not in csv_dict:
                    csv_dict[key] = node.attrib.get(att)

    # Process children
    for child in node:
        visited_child.append(child)
        child_visited_list, child_out_buf = node_process(child, ignore)
        out_buf += ' ' + child_out_buf
        visited_child.extend(child_visited_list)

    # Closing tag and formatting
    if tag in config and config[tag]['main-config'] is not None:
        if "tag" in config[tag]['main-config']:
            out_buf += "</" + node.tag + ">"

        if "newLine" in config[tag]['main-config']:
            out_buf += '\n'
        elif 'doubleNewLine' in config[tag]['main-config']:
            out_buf += '\n\n'

        parent = node.getparent()
        if parent is not None and parent.tag is not None:
            parent_tag = strip_ns(parent.tag)
            if parent_tag in config and config[parent_tag]['main-config'] is not None:
                if node.tail is not None:
                    out_buf += node.tail.replace('\n', ' ')

        if ignore:
            out_buf = ''

    return visited_child, out_buf



for dirpath, subdirs, files in os.walk(rootdir):
    for filename in files:
        if filename.endswith(".xml"): # only processing XML files
            csv_dict['Filename'] = filename
            filePath = os.path.join(dirpath, filename)
            print('processing... ' + filePath)
            old_ext = filename.split(".")[-1]
            output_file = filename.replace(old_ext, 'txt')
            f = open(destdir+"/"+output_file, mode='w',encoding='ascii', errors='ignore')
            tree = etree.parse(filePath)
            treeroot = tree.getroot()
            # Convert all tag names to uppercase
            for elem in treeroot.iter():
                elem.tag = strip_ns(elem.tag).upper()
            print(tree)
            print(treeroot)
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
                if len(line) > 80:
                    i = 0
                    while i+80 < len(line):
                        indice_lastspace = line[i:i+80].rfind(' ')
                        if indice_lastspace == -1:
                            break
                        str_to_write += line[i:i+indice_lastspace].strip() + '\n'
                        i += indice_lastspace + 1
                    str_to_write += line[i:].strip() + '\n'
                else:
                    str_to_write += line.strip() + '\n'
            pages = len(treeroot.findall('.//PB'))
            wordcount = len(str_to_write.split())
            csv_dict['Pages'] = pages
            csv_dict['WordCount'] = wordcount
            csvwriter.writerow(csv_dict)

            print(str_to_write)
            f.write(str_to_write)
            f.close()
            break
            



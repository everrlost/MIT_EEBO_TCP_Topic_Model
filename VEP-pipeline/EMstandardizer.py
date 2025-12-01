#formerly EMstandardizer-new-p
import argparse
import os
import csv
import pickle
import re
import string
from collections import defaultdict
import operator
import copy
import time
import pandas as pd
from multiprocessing import Pool, Manager, cpu_count
from functools import partial

parser = argparse.ArgumentParser(description='early modern standardizer (VARD alternative) - works on early modern english text files')
parser.add_argument('corpus_path', help='path to corpus to tag relative to the location of this script')
parser.add_argument('output_path', help='path to output relative to the location of this script')
parser.add_argument('plaintext_dictionary', help='path to context sensitive rule .txt file')
parser.add_argument('--archaic_endings', help='leave archaic endings in (flag as 1 in dictionary files)',action='store_true')
parser.add_argument('--token_csv', help='generate token csvs', action='store_true')
parser.add_argument('--num_processes', type=int, default=None, help='number of processes to use (default: number of CPU cores)')

#flag meanings: 1 = archaic ending (leave in), 2 = archaic ending to swap out, 0 = rule will be applied in all cases
#the intention is that all rules with 1 flag have a corresponding 2 flag rule with a shared stem ie sayeth -> said and sayeth -> sayeth
#that way, no two rules with the same key get entered in the dictionary

#the same (relatively) lossless token simplification scheme used in Ubiq
def end_reason(token, words, i):
    if token[0].isalpha():
        return 'c'
    elif (token[0] == u'\n') or (token[0] == '\n'):
        i = 0
        r = ''
        while i < (len(token)):
            r = r + 'n'
            i = i + 1
        return r
    elif token[0] in string.punctuation:
        return 'c'
    else:
        #s for whitespace
        return 's'

#generates formatted tokens for csv output
def getToken(word, words, i, rule='', flag='', tagind=''):
    try:
        er = end_reason(words[i + 1], words, i + 1)
    except IndexError:
        er = 's'
    if rule != '':
        return ([word, word.lower(), er, 'Standardized', tagind, ' '.join(rule)])
    # Note: replaceWord and researched_words need to be passed as parameters
    # This will be handled in the process_file function
    return([word, word.lower(), er, '', tagind, ''])

#helper: identifies case, mostly
#lowercase = lowercase, allcaps = allcaps, all other case variations default to Title case
def getCaseType(word):
    if word.islower():
        return 'l'
    elif word.isupper():
        return 'u'
    else:
        return 't'

#helper: alters case type for standardization
def changeToCaseType(word, caseType):
    if caseType == 'l':
        return word.lower()
    elif caseType == 'u':
        return word.upper()
    else:
        return string.capwords(word)

#given a word that is NOT part of a rule, return its original form or a standardized form
def replaceWord(word, standard_d, corrections_made, file_corrections, file_tokens, curFile):
    caseType = getCaseType(word)
    if word.lower() in standard_d:
        fix = standard_d[word.lower()][0]
        corrections_made[(word.lower(), fix)] += 1
        file_corrections[curFile] += 1
        file_tokens[curFile] += 1
        return changeToCaseType(fix, caseType)
    else:
        return word

#compiles two dictionaries based on rule type: standard_d (1-1) and long_d (1-many, many-many, many-1)
def compileDictionaries(path, endings):
    standard_d = {}
    long_d = {}
    errorFlag = False
    with open(path, mode='r', encoding='utf-8') as dfile:
        for line in dfile:
            line = line.lower()
            if line != '' and line != '\n' and line != ' ' and line[0] != '#':
                trio = line.strip('\n').split(":")
                l, r, flag = trio[0].split(','), trio[1].split(','), int(trio[2])
                if flag == 0 or (endings and flag == 1) or (endings == False and flag == 2):
                    entry = (l, r)
                    if len(l) == 1 and len(r) == 1:
                        if l[0] not in standard_d:
                            standard_d[l[0]] = r
                        else:
                            if r != standard_d[l[0]]:
                                print('Duplicate key/multiple value error!', l[0], r, standard_d[l[0]])
                                errorFlag = True
                    elif l[0] not in long_d:
                        if l[0] in standard_d:
                            print('Duplicate key/multiple value error!', l[0], r, standard_d[l[0]])
                            errorFlag = True
                        else:
                            long_d[l[0]] = [entry]
                    else:
                        y = l[0]
                        x = long_d[y]
                        for curEnt in x:
                            if curEnt[0] == l and curEnt[1] != r:
                                print('Duplicate key/multiple value error!', l[0], r, curEnt[1])
                                errorFlag = True
                        x.append(entry)
                        long_d[y] = x
    if errorFlag:
        print("Please reconcile dictionary errors.")
        exit(1)
    return standard_d, long_d

def process_file(file_info, standard_d, long_d, researched_words, output_path, token_csv):
    """Process a single file - this function will be run in parallel"""
    root, filename = file_info
    
    # Local counters for this process
    local_corrections_made = defaultdict(int)
    local_file_corrections = defaultdict(int)
    local_file_tokens = defaultdict(int)
    
    file_path = os.path.join(root, filename)
    
    if '.txt' not in file_path:
        return filename, None, None, None  # Return as bad file
    
    try:
        #generate output paths
        o_path = os.path.join(output_path, filename)
        text_file = open(file_path, "r", encoding='utf-8')
        
        tokens = []
        if token_csv:
            t_path = os.path.join(output_path, "Token_CSV")
            if not os.path.exists(t_path):
                os.makedirs(t_path, exist_ok=True)

        #initialize current file
        curFile = file_path
        local_file_corrections[curFile] = 0
        local_file_tokens[curFile] = 0
        contents = text_file.read()
        
        #tokenize
        words = re.findall(r'[\^A-z\']+(?:[\-\'\*\`]?[\^A-z])*|[0-9]*[\.]?[0-9]+|[ ]+|[\n]+|[^a-zA-Z0-9\^ \n]+',contents)
        
        #empty dict is falsy, but a 1:1 dictionary will result in empty long_d
        if long_d:
            line = []
            i = 0
            while i < (len(words)):
                word = words[i]
                ruleFound = False
                if word.lower() in long_d:
                    #traverse phrase
                    rules = long_d[word.lower()]
                    for rule in rules:
                        j = i
                        r = 0
                        cases = []
                        caseType = 'l'
                        while(j < len(words)):
                            cur = words[j].lower()
                            target = rule[0][r]
                            if target == '.' and cur != target:
                                break
                            if ' ' not in cur and '\n' not in cur and cur != target:
                                break
                            elif cur == target:
                                #remember cases of traversed words to preserve capitalization patterns
                                if cur != '.':
                                    #periods take the "case type" of the previous word
                                    #such that St. Bede becomes Saint Bede and st. bede becomes saint bede
                                    caseType = getCaseType(words[j])
                                cases.append(caseType)
                                r += 1
                                if r == len(rule[0]):
                                    ruleFound = True
                                    break
                            j+=1
                        if ruleFound:
                            local_corrections_made[(tuple(rule[0]), tuple(rule[1]))] +=1
                            local_file_corrections[curFile] += 1
                            local_file_tokens[curFile] += len(rule[0])
                            caps = 'l'
                            for k in range(len(rule[1])):
                                if k < len(rule[0]):
                                    caps = cases[k]
                                repl = changeToCaseType(rule[1][k], caps)
                                if token_csv and '\n' not in word and ' ' not in word:
                                    tokens.append(getToken(repl, words, i, rule=rule[0], tagind=k))
                                line.append(repl)
                                if k < len(rule[1]) - 1:
                                    #adds spaces between words (handles rules where left and right sides are of dif. lengths)
                                    if rule[1][k + 1] != '.':
                                        line.append(' ')
                            i = j
                            break
                    if not ruleFound:
                        if token_csv and '\n' not in word and ' ' not in word:
                            # Simplified getToken for non-rule words
                            try:
                                er = end_reason(words[i + 1], words, i + 1)
                            except IndexError:
                                er = 's'
                            
                            # Check if word needs replacement
                            replaced_word = replaceWord(word, standard_d, local_corrections_made, 
                                                      local_file_corrections, local_file_tokens, curFile)
                            if replaced_word != word:
                                tokens.append([replaced_word, replaced_word.lower(), er, 'Standardized', 0, word])
                            elif word.lower() in researched_words:
                                tokens.append([word, word.lower(), er, 'Researched', 0, ''])
                            else:
                                tokens.append([word, word.lower(), er, '', 0, ''])
                        
                        line.append(replaceWord(word, standard_d, local_corrections_made, 
                                              local_file_corrections, local_file_tokens, curFile))
                else:
                    if token_csv and '\n' not in word and ' ' not in word:
                        # Simplified getToken for non-rule words
                        try:
                            er = end_reason(words[i + 1], words, i + 1)
                        except IndexError:
                            er = 's'
                        
                        # Check if word needs replacement
                        replaced_word = replaceWord(word, standard_d, local_corrections_made, 
                                                  local_file_corrections, local_file_tokens, curFile)
                        if replaced_word != word:
                            tokens.append([replaced_word, replaced_word.lower(), er, 'Standardized', 0, word])
                        elif word.lower() in researched_words:
                            tokens.append([word, word.lower(), er, 'Researched', 0, ''])
                        else:
                            tokens.append([word, word.lower(), er, '', 0, ''])
                    
                    line.append(replaceWord(word, standard_d, local_corrections_made, 
                                          local_file_corrections, local_file_tokens, curFile))
                i+=1
        else:
            # Handle case where long_d is empty
            line = []
            for i, word in enumerate(words):
                if token_csv and '\n' not in word and ' ' not in word:
                    # Simplified getToken for non-rule words
                    try:
                        er = end_reason(words[i + 1], words, i + 1)
                    except IndexError:
                        er = 's'
                    
                    # Check if word needs replacement
                    replaced_word = replaceWord(word, standard_d, local_corrections_made, 
                                              local_file_corrections, local_file_tokens, curFile)
                    if replaced_word != word:
                        tokens.append([replaced_word, replaced_word.lower(), er, 'Standardized', 0, word])
                    elif word.lower() in researched_words:
                        tokens.append([word, word.lower(), er, 'Researched', 0, ''])
                    else:
                        tokens.append([word, word.lower(), er, '', 0, ''])
                
                line.append(replaceWord(word, standard_d, local_corrections_made, 
                                      local_file_corrections, local_file_tokens, curFile))

        # if token csvs are enabled (they exist mainly for internal usage) write out tokens and annotations in separate files
        if token_csv:
            csv_outpath = os.path.join(output_path, "Token_CSV", filename.strip('.txt') + '_tokens.csv')
            with open(csv_outpath, mode='w', encoding="utf-8") as c:
                cwriter = csv.writer(c, lineterminator='\n')
                cwriter.writerow(["token", "tokenToMatch", "endReason", "tag", "tagIndex"])
                for row in tokens:
                    cwriter.writerow(row[:-1])
            an_outpath = os.path.join(output_path, "Token_CSV", filename.strip('.txt') + '_annotations.csv')
            with open(an_outpath, mode='w', encoding="utf-8") as a:
                cwriter = csv.writer(a, lineterminator='\n')
                cwriter.writerow(["tokenIndex", "original"])
                i = 0
                for row in tokens:
                    if row[3] == 'Standardized':
                        cwriter.writerow([i, row[5]])
                    i += 1

        #merge words back together, write to file
        fline = ''.join(line)
        with open(o_path, "w", encoding='utf-8') as output_file:
            output_file.write(fline)
        text_file.close()
        
        return None, local_corrections_made, local_file_corrections, local_file_tokens
        
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return filename, None, None, None

def merge_dictionaries(dict_list):
    """Merge a list of defaultdict objects"""
    merged = defaultdict(int)
    for d in dict_list:
        if d is not None:
            for key, value in d.items():
                merged[key] += value
    return merged

if __name__ == '__main__':
    args = parser.parse_args()
    output_path, dict_path, endings = args.output_path, args.plaintext_dictionary, args.archaic_endings
    num_processes = args.num_processes or cpu_count()
    
    print(f"Using {num_processes} processes for parallel processing")
    
    #import dictionary
    standard_d = {}
    long_d = {}
    if dict_path:
        standard_d, long_d = compileDictionaries(dict_path, endings)

    # Load researched words (note: the original code had an issue here - it opened but never loaded the pickle)
    researched_words = []
    try:
        with open(r"C:\Users\Ian7G\OneDrive\Documents\VEP Processing\VEP-pipeline\researched_words.pickle", mode='rb') as r_file:
            researched_words = pickle.load(r_file)
    except FileNotFoundError:
        print("Warning: researched_words.pickle not found, continuing without researched words")
        researched_words = []

    #create output directory if it does not already exist
    if not os.path.isdir(output_path):
        os.makedirs(output_path, exist_ok=True)

    # Collect all files to process
    file_list = []
    for root, dirnames, filenames in os.walk(args.corpus_path):
        for filename in filenames:
            file_list.append((root, filename))

    print(f"Found {len(file_list)} files to process")
    print("Standardizing corpus", args.corpus_path)

    # Process files in parallel
    bad_files = []
    all_corrections_made = []
    all_file_corrections = []
    all_file_tokens = []

    # Create a partial function with the shared parameters
    process_func = partial(process_file, 
                          standard_d=standard_d, 
                          long_d=long_d, 
                          researched_words=researched_words,
                          output_path=output_path,
                          token_csv=args.token_csv)

    # Use multiprocessing Pool
    with Pool(processes=num_processes) as pool:
        results = []
        
        # Submit all jobs
        for i, file_info in enumerate(file_list):
            result = pool.apply_async(process_func, (file_info,))
            results.append(result)
        
        # Collect results with progress reporting
        for i, result in enumerate(results):
            if (i + 1) % 50 == 0:
                print(f"{i + 1} files completed.")
            
            bad_file, corrections_made, file_corrections, file_tokens = result.get()
            
            if bad_file is not None:
                bad_files.append(bad_file)
            else:
                all_corrections_made.append(corrections_made)
                all_file_corrections.append(file_corrections)
                all_file_tokens.append(file_tokens)

    # Merge all the results from different processes
    final_corrections_made = merge_dictionaries(all_corrections_made)
    final_file_corrections = merge_dictionaries(all_file_corrections)
    final_file_tokens = merge_dictionaries(all_file_tokens)

    if bad_files:
        print('Unable to read the following files: ', bad_files)
    
    metadata_path = os.path.join(os.path.dirname(args.corpus_path),os.path.basename(args.corpus_path)+'-correction-stats.csv')
    corrections_per_file = os.path.join(os.path.dirname(args.corpus_path),os.path.basename(args.corpus_path)+'-corrections-per-file.csv')
    
    # write out corrections metadata
    with open(metadata_path, 'w') as g:
        #corpus-level correction frequencies, order from most to least frequently performed
        header = ["Original", "Normalized", "Frequency"]
        writer = csv.writer(g, delimiter=',', quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
        writer.writerow(header)
        for k, v in sorted(final_corrections_made.items(), key=operator.itemgetter(1), reverse=True):
            orig = k[0]
            cor = k[1]
            if isinstance(k[0], tuple):
                orig = ' '.join(k[0])
            if isinstance(k[1], tuple):
                cor = ' '.join(k[1])
            writer.writerow([orig, cor, v])
    
    with open(corrections_per_file, 'w') as g:
        #corrections per file
        header = ["Filepath", "# of Corrections","# of Corrected Tokens"]
        writer = csv.writer(g, delimiter=',', quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
        writer.writerow(header)
        for k, v in final_file_corrections.items():
            cfilename = k
            cor = v
            tok = final_file_tokens[k]
            writer.writerow([cfilename, cor, tok])
    
    print(f"Job completed using {num_processes} processes, corrections statistics written to", metadata_path, "and", corrections_per_file)
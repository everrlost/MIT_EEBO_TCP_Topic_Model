import logging
from pathlib import Path

import nltk
from nltk.corpus import stopwords #stopwords are words we will want to ignore
from nltk.stem import PorterStemmer #reduce words to just stems
import numpy as np
import pandas as pd
from tqdm import tqdm
from gensim import corpora
from gensim.models import LdaModel, LdaMulticore, CoherenceModel

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)

try:
    nltk.data.find('corpora/stopwords') #if stopwords are not downloaded, download them
except LookupError:
    nltk.download('stopwords')

STEMMER = PorterStemmer()
STOPWORDS = set(stopwords.words('english')) #set stopwords to english

def load_text(input_folder):
    folder = Path(input_folder)
    files = sorted(folder.glob('*.txt')) #get all the .txt files in the folder 
    logging.info(f'Found {len(files)} txt files in {input_folder}')
    #curly braces means dictionary and creates a mapping of file name to text content
    texts = {}
    for file in tqdm(files, desc='Loading text files'):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                texts[file.stem] = f.read() #file.stem is the name of the file without the extension
        except Exception as e:
            logging.warning(f"skipping {file}: {e}")
    return texts

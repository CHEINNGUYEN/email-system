import numpy as np
import pandas as pd
import re
from sklearn.base import BaseEstimator, TransformerMixin
from nltk.stem import SnowballStemmer

stemmer = SnowballStemmer('english')

class CustomFeatures(BaseEstimator, TransformerMixin):
    """
    Extracts custom numerical features from raw email text:
    - Message length
    - Number of digits
    - Presence of currency symbols ($ £ €)
    - Presence of URLs (http / www)
    """
    def fit(self, X, y=None): 
        return self
    
    def transform(self, X):
        features = []
        for text in X:
            text = str(text) if pd.notna(text) else ""
            length = len(text)
            num_digits = sum(c.isdigit() for c in text)
            has_currency = int(bool(re.search(r'[\$£€]', text)))
            has_url = int(bool(re.search(r'(http|www)', text.lower())))
            features.append([length, num_digits, has_currency, has_url])
        return np.array(features)

class TextCleaner(BaseEstimator, TransformerMixin):
    """
    Cleans raw text data by:
    - Keeping only alphanumeric characters, spaces, and specific symbols (! $ £ €)
    - Converting to lowercase
    - Applying SnowballStemmer for better word root extraction
    """
    def fit(self, X, y=None): 
        return self
    
    def transform(self, X):
        cleaned_X = []
        for text in X:
            text = str(text) if pd.notna(text) else ""
            # Keep letters, numbers, spaces, and ! $ £ €
            filtered = ''.join(c if c.isalnum() or c.isspace() or c in '$£€!' else ' ' for c in text)
            words = filtered.lower().split()
            cleaned_X.append(' '.join([stemmer.stem(w) for w in words]))
        return cleaned_X


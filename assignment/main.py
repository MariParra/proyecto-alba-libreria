from asignacion.utils import requirements
import pandas as pd
import glob
import os
from rapidfuzz import process, fuzz

# -- PACKAGES --
requirements()

# -- CONFIG --
FILES_FOLDER = './files'
CATALOG_FILE = 'catalog.csv'
FORMULARIO =  'forms.csv'
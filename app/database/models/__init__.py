
# This file is a central import file. Its purpose is to make imports to Alembic more convinient.
# Instead of modifying the imports in env.py in the alembic folder, we can just import all of our models here.
# Ignore the warning from pylance. Alembic can still access the class.

from .models import *


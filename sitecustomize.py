from datetime import date
from decimal import Decimal
import builtins

from fastapi.encoders import jsonable_encoder

# Tijdelijke import-alignment voor runtimepaden die globale namen gebruiken
# zonder expliciete import in app/main.py. Dit houdt gedrag verder ongewijzigd
# en voorkomt 500-fouten op de JSON debug-export route.
builtins.date = date
builtins.Decimal = Decimal
builtins.jsonable_encoder = jsonable_encoder

# Frontend patch workflow

Grote frontendbestanden mogen niet meer via volledige file-overwrites worden aangepast.

Voor bestanden groter dan 500 regels, zoals `KassaPage.jsx`, `Voorraad.jsx` en grote routerbestanden, geldt:

1. maak een leesbare unified diff patch;
2. pas de patch lokaal toe;
3. test de geraakte route;
4. commit pas na succesvolle test.

Dit voorkomt regressies door onbedoelde overschrijvingen van monolithische React-bestanden.

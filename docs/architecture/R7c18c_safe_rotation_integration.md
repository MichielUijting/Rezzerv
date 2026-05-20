# R7c-18c â€” Safe Rotation Integration

Deze lokale patch integreert safe rotation preprocessing vÃ³Ã³r image-OCR.

Regels:
- alleen rotation-only;
- geen crop;
- geen perspective warp;
- fallback naar originele afbeelding bij twijfel;
- hoek moet binnen 45 graden blijven;
- confidence moet minimaal 0.55 zijn.

R7c-18b bewees:
- AH foto 3 mag veilig roteren;
- Jumbo foto 1 wordt geblokkeerd;
- PLUS foto 1 wordt geblokkeerd.

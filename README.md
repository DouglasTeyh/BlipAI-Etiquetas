# BlipAI-Etiquetas

Aplicativo Windows para impressão térmica de etiquetas (PPLB / RAW) integrado com o Webhook BlipAI / Casa do Bebê.

## Build Automático (.exe)
Toda alteração enviada para o branch `main` ou qualquer acionamento manual de workflow executa o GitHub Actions em runner `windows-latest` e gera o executável `BlipAI-Etiquetas.exe` como Artifact e Release.

## Execução Local
Requer Python 3.8+:
```bash
pip install -r requirements.txt
python painel_automata.py
```

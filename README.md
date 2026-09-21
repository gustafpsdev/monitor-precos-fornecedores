# Monitor de Preços de Fornecedores

![Python](https://img.shields.io/badge/Python-3.11+-496B86?logo=python&logoColor=white) ![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-web-68717A) ![Status](https://img.shields.io/badge/status-protótipo-68717A)

Automação em Python para consultar páginas de produtos, extrair preços por seletor CSS, registrar histórico e sinalizar alterações relevantes.

## Recursos

- Leitura de produtos a partir de CSV
- Extração de preços com BeautifulSoup e lxml
- Histórico de preços em CSV
- Limite percentual configurável para alertas
- Integração opcional com webhook do Microsoft Teams

## Execução

```bash
pip install -r requirements.txt
cp produtos.exemplo.csv produtos.csv
python monitor_precos.py
```

Para alertas no Teams, defina a variável `TEAMS_WEBHOOK_URL`. Respeite os termos de uso, o `robots.txt` e os limites dos sites consultados.


## Arquitetura

```text
produtos.csv
     ↓
Coleta HTTP + seletor CSS
     ↓
Normalização e comparação
     ├── histórico CSV
     └── alerta opcional no Teams
```

URLs, seletores reais, histórico e webhook permanecem fora do versionamento.

## Licença

Distribuído sob a licença MIT. Consulte o arquivo [LICENSE](LICENSE).

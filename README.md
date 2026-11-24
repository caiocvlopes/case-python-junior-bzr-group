## Setup inicial (ambiente virtual + db)
```bash
docker compose up -d
python -m venv .venv
.\.venv\Scripts\activate
python .\scripts\setup_db.py
```

## Limpeza

Só usa a biblioteca padrão (Python 3.10+), não precisa do banco.

```bash
python .\scripts\clean_data.py
python -m unittest discover -s scripts
```

Gera em `saida/`: `precatorios.csv`, `pagamentos.csv` e `relatorio.md` (corrigido, descartado e em dúvida). Os arquivos de `dados/` não são alterados.

Para carregar a base no banco (com o venv ativo e `pip install -r requirements.txt`):

```bash
python .\scripts\load_data.py
```

A carga só roda com as tabelas vazias. Para recomeçar do zero (apaga o banco): `docker compose down -v`, `docker compose up -d` e `python .\scripts\setup_db.py`.

## Uso de IA

Usei o Claude Code (Claude Sonnet 5.5, da Anthropic) no `DIAGNOSTICO.md` e na limpeza.

Na limpeza, a IA escreveu `clean_data.py` e os testes a partir das regras do diagnóstico. A conferência foi rodar os testes e comparar os totais por processo com a tabela do diagnóstico. Como os dois vêm da mesma análise, isso confirma a consistência, não as premissas. A IA também escreveu `load_data.py` e o testou em um banco recriado: 6 precatórios, 8 pagamentos, total pago de 34.200,50 e segunda carga recusada.

Sobre o diagnóstico:

Antes de pedir ajuda, li os arquivos e anotei o que já tinha achado: `evento_id` repetido, processo com 25 caracteres contra `CHAR(20)`, processo vazio, `valor` e datas fora do padrão, `tipo` e `atualizado_em`. Pedi que a IA completasse o diagnóstico no formato do enunciado, com texto enxuto, e deixei limpeza e prevenção para as próximas etapas.

A IA leu todos os arquivos, inclusive os que não estavam na minha primeira leitura (`hub.csv`, `tribunal.csv` e `apresentacoes.json`), escreveu scripts para contar e cruzar os registros, testou o comportamento do Postgres do `docker-compose.yml` em tabelas temporárias e redigiu o texto. Nada em `dados/` foi alterado. Ela trouxe achados que eu não tinha, como o estorno somado como pagamento, os prazos errados do `hub.csv` e o `tribunal.csv` salvo em outro encoding, e corrigiu um palpite meu: o `ev-001` repetido é uma versão corrigida do mesmo evento, não um estorno.

Como o resultado foi conferido:

- Os números de linha e os trechos citados no diagnóstico foram conferidos por script contra os arquivos originais. Os totais e os prazos saíram de um script de análise. Os dois scripts ficaram fora do repositório.
- O que o texto diz sobre o banco (`10/04/2025` lido como 4 de outubro, `CHAR(20)` rejeitando o CNJ, constraints) foi testado no Postgres do projeto. Os comandos estão no fim do `DIAGNOSTICO.md`.
- O script de importação não está no repositório, então o que o texto diz sobre ele vem do enunciado. As premissas que os dados não provam estão marcadas como "a confirmar com o tribunal".
- Na revisão apareceu um trecho que dizia "testado" sem ter sido testado. Foi corrigido.

## Setup inicial (ambiente virtual + db)
```bash
docker compose up -d
python -m venv .venv
.\.venv\Scripts\activate
python .\scripts\setup_db.py
```

## Uso de IA

Usei o Claude Code (Claude Sonnet 5.5, da Anthropic) para escrever o `DIAGNOSTICO.md`. Foi só nessa etapa.

Antes de pedir ajuda, li os arquivos e anotei o que já tinha achado: `evento_id` repetido, processo com 25 caracteres contra `CHAR(20)`, processo vazio, `valor` e datas fora do padrão, `tipo` e `atualizado_em`. Pedi que a IA completasse o diagnóstico no formato do enunciado, com texto enxuto, e deixei limpeza e prevenção para as próximas etapas.

A IA leu todos os arquivos, inclusive os que não estavam na minha primeira leitura (`hub.csv`, `tribunal.csv` e `apresentacoes.json`), escreveu scripts para contar e cruzar os registros, testou o comportamento do Postgres do `docker-compose.yml` em tabelas temporárias e redigiu o texto. Nada em `dados/` foi alterado. Ela trouxe achados que eu não tinha, como o estorno somado como pagamento, os prazos errados do `hub.csv` e o `tribunal.csv` salvo em outro encoding, e corrigiu um palpite meu: o `ev-001` repetido é uma versão corrigida do mesmo evento, não um estorno.

Como o resultado foi conferido:

- Os números de linha e os trechos citados no diagnóstico foram conferidos por script contra os arquivos originais. Os totais e os prazos saíram de um script de análise. Os dois scripts ficaram fora do repositório.
- O que o texto diz sobre o banco (`10/04/2025` lido como 4 de outubro, `CHAR(20)` rejeitando o CNJ, constraints) foi testado no Postgres do projeto. Os comandos estão no fim do `DIAGNOSTICO.md`.
- O script de importação não está no repositório, então o que o texto diz sobre ele vem do enunciado. As premissas que os dados não provam estão marcadas como "a confirmar com o tribunal".
- Na revisão apareceu um trecho que dizia "testado" sem ter sido testado. Foi corrigido.

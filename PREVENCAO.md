# Prevenção

O SQL e o novo importador de pagamentos foram escritos e testados; as mudanças de processo são propostas. Os números entre parênteses são os itens do [DIAGNOSTICO.md](DIAGNOSTICO.md).

## Processo

- Guardar o anexo do tribunal como chegou, com data e hash. Ninguém abre e salva por cima; quem quiser olhar no Excel usa uma cópia (9, 10).
- Trocar a conferência manual por uma comparação automática pelo processo em 20 dígitos e pelo ente normalizado. O operador recebe só as divergências reais (5, 6, 9).
- Toda importação termina com um resumo (recebidos, aplicados, ignorados por repetição, rejeitados) enviado a um responsável nomeado. Pendência aberta é revisada toda semana (3).
- Toda semana, comparar o total pago e o valor de face com o tribunal, por processo.
- Pedir ao tribunal um leiaute versionado que diga: janela do arquivo, papel do `atualizado_em`, como o estorno aponta o pagamento original, fuso, campos obrigatórios e aviso antes de mudanças (11).

## Script de importação

Está em [`scripts/importar_pagamentos.py`](scripts/importar_pagamentos.py) e roda depois da migração:

```bash
python .\scripts\importar_pagamentos.py .\dados\pagamentos.json
```

Ele importa só o `pagamentos.json`. A carga semanal da lista de precatórios não foi escrita, e o resumo sai no terminal, sem envio ao responsável. O que ele faz:

1. Confere o formato do arquivo (UTF-8, lista JSON, campos presentes). Se estiver errado, rejeita o arquivo inteiro e não grava nada (11).
2. Guarda cada registro como veio em `evento_recebido`, antes de qualquer conversão.
3. Converte de forma explícita, com as mesmas funções do `clean_data.py`: dinheiro em `Decimal`, datas enviadas ao banco como `date`, processo em 20 dígitos (6, 7, 8). O que for ambíguo não é adivinhado.
4. Escolhe a versão vigente de cada `evento_id` pelo `atualizado_em`, comparando com tudo o que já foi recebido. Se a vigente for inválida, o evento sai do total e vira pendência, sem voltar para a versão antiga. Mesmo `atualizado_em` com conteúdo diferente também vira pendência (1).
5. Grava com *upsert*, nunca somando (1, 2):

```sql
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (evento_id) DO UPDATE SET
    precatorio_id = EXCLUDED.precatorio_id,
    tipo          = EXCLUDED.tipo,
    valor         = EXCLUDED.valor,
    pago_em       = EXCLUDED.pago_em,
    atualizado_em = EXCLUDED.atualizado_em
WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em;
```

6. Usa uma transação por arquivo. Registro ruim vira linha com `erro` e não derruba os outros; falha do programa desfaz tudo, e rodar de novo é seguro (1, 3).

Os testes em [`scripts/test_importar_pagamentos.py`](scripts/test_importar_pagamentos.py) usam um banco temporário e cobrem: arquivo do case rodado duas vezes (total 34.200,50 e 3 pendências), versão fora de ordem, versão vigente inválida, empate, registro ruim e arquivo fora do formato.

## Banco

O SQL completo está em [`sql/prevencao.sql`](sql/prevencao.sql). Ele altera o schema atual:

| Mudança | Evita |
| --- | --- |
| `UNIQUE (evento_id)` e coluna `atualizado_em` em `pagamento` | evento contado duas vezes (1) |
| View `total_pago`, com estorno subtraindo | soma errada guardada em algum lugar (2) |
| Tabelas `importacao` e `evento_recebido`, view `pendencia` | rejeição sem rastro (3) |
| `apresentado_em` e `prazo_pagamento` como coluna gerada | prazo divergente da regra (4) |
| `situacao` em `precatorio` | dado em dúvida parecendo confirmado (5) |
| `CHECK` de 20 dígitos no processo | chave em formatos diferentes (6) |
| Tabela `ente` com chave estrangeira | o mesmo ente com várias grafias (9) |
| `CHECK (valor_face > 0)` | valor de face zerado ou negativo |

O `CHAR(20)` foi mantido: o banco guarda só os dígitos e a formatação CNJ é feita na exibição.

Testei em uma cópia do banco já carregado: a migração aplicou, os totais por processo continuaram iguais, os prazos de 02/04, 03/04 e 29/02 saíram certos, reenviar uma versão antiga ou repetida não mudou nada, e o banco recusou evento duplicado, processo curto, ente com outra grafia e prazo escrito à mão.

Para aplicar (com o venv ativo, depois do `load_data.py`):

```bash
python .\scripts\aplicar_prevencao.py
```

O script recusa rodar duas vezes ou sem o schema criado, e se a migração falhar o banco fica como estava.

Antes de aplicar:

- A base precisa estar limpa; com duplicatas, a migração falha inteira.
- `scripts/load_data.py` foi feito para o schema atual. Depois da migração ele precisa gravar `ente`, `atualizado_em`, `apresentado_em` e `situacao`.
- As linhas já carregadas ficam com `atualizado_em` em 1970 e sem histórico, então a primeira versão importada as substitui, mesmo que seja antiga. Preencha a coluna a partir de `saida/pagamentos.csv` antes de importar arquivos antigos.

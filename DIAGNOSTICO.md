# Diagnóstico

Arquivos analisados: `pagamentos.json`, `apresentacoes.json`, `tribunal.csv`, `hub.csv`, `schema.sql`, `DOCUMENTACAO_TRIBUNAL.md` e o fluxo do `ENUNCIADO.md`. Os números de linha são os do arquivo; nos CSV, a linha 1 é o cabeçalho.

O script de importação não está no repositório (o `scripts/setup_db.py` só aplica o schema), então o que afirmo sobre ele vem dos passos 2 e 5 do enunciado. O comportamento do banco foi testado no Postgres 16 do `docker-compose.yml`; os comandos estão no fim.

Os itens vão do mais grave para o menos grave, pelo impacto direto no negócio. O 11 fica por último, mas é causa de vários dos anteriores.

## Visão geral

Os números não batem por três razões que se acumulam. A importação soma tudo o que chega, sem olhar identidade, versão ou tipo do evento (1 e 2), e descarta em silêncio o que o banco rejeita (3). A conferência com o tribunal falha porque cada arquivo escreve o processo de um jeito e a comparação é por texto exato, no Excel (6 e 9), o que esconde divergências reais (5). O prazo tem um erro de regra à parte (4). A documentação do tribunal já não descreve os arquivos (11) e está na origem de boa parte dos defeitos.

Efeito no total pago, por processo:

| Processo                    | Soma de todas as linhas | O que os dados sustentam | Itens   |
| --------------------------- | ----------------------: | -----------------------: | ------- |
| `0012345-10.2019.8.26.0053` |               35.501,00 |                18.000,50 | 1       |
| `0023456-21.2020.8.26.0053` |                9.200,00 |                 9.200,00 | 3, 6, 7 |
| `0034567-32.2018.8.26.0405` |               10.000,00 |                     0,00 | 2       |
| `0045678-43.2021.5.02.0011` |                3.000,00 |                 3.000,00 |         |
| `0056789-54.2017.4.03.6100` |                 -200,00 |                     0,00 | 7       |
| `0067890-65.2016.8.26.0053` |                4.000,00 |                 4.000,00 | 5       |
| Total                       |               61.501,00 |                34.200,50 |         |

A soma de todas as linhas é a leitura literal do passo 2: somar o `valor` de cada linha do arquivo, já convertendo o texto e casando o processo pelos dígitos, que é o melhor cenário para a importação atual. A coluna da direita fica com a versão mais recente de cada evento e subtrai o estorno. A diferença é de R$ 27.300,50. Em `0023456` os dois valores coincidem só porque o `ev-005` foi casado pelos dígitos (item 6) e o `ev-004` ficou de fora, sem valor. No total ainda sobram três eventos sem destino: `ev-004`, `ev-009` (-200) e `ev-010` (R$ 750,00, sem processo).

Premissas das contas e dos prazos, todas a confirmar com o tribunal: vale a versão de `atualizado_em` mais recente; estorno subtrai; `2.500,50` e `10/04/2025` estão no formato brasileiro; o prazo conta pela data de Brasília.

| #   | Problema                                                       | Relação                                 |
| --- | -------------------------------------------------------------- | --------------------------------------- |
| 1   | Evento repetido ou corrigido é somado de novo                  | Causa do total inflado                  |
| 2   | Estorno é somado como pagamento                                | Consequência de 1 e 11                  |
| 3   | Eventos que o banco rejeita somem sem aviso                    | Causa; amplifica 6 e 7                  |
| 4   | Prazo do hub errado em 2 dos 5 precatórios                     | Independente                            |
| 5   | `tribunal.csv` e `hub.csv` divergem em valor, ente e cobertura | Em parte real, em parte efeito de 6 e 9 |
| 6   | Processo sem forma única; `CHAR(20)` não comporta o CNJ        | Causa de 5 e 9                          |
| 7   | `valor` fora do formato documentado                            | Consequência de 11                      |
| 8   | `data_pagamento` em DD/MM/AAAA vira outro mês                  | Consequência de 11                      |
| 9   | Conferência no Excel por texto exato                           | Consequência de 6 e 10                  |
| 10  | `tribunal.csv` fora do layout documentado                      | Consequência do passo 3 e de 11         |
| 11  | A documentação não descreve os arquivos                        | Causa de 1, 2, 7, 8 e 10                |

## 1. Evento repetido ou corrigido é somado de novo

**Evidência**

- `pagamentos.json` tem 13 registros e 11 `evento_id` distintos.
- `ev-002` aparece duas vezes, idêntico (linhas 10-17 e 26-33).
- `ev-001` aparece duas vezes com conteúdo diferente: linhas 2-9 (`valor` 15000.0, `atualizado_em` 2025-03-10T10:00) e linhas 66-73 (`valor` 15500.0, `atualizado_em` 2025-03-11T09:00). Mesmo processo e mesma `data_pagamento`: é o mesmo evento corrigido no dia seguinte, não um estorno (o estorno tem `evento_id` e `tipo` próprios, ver 2). A ordem no arquivo não pode ser o critério; quem diz qual versão vale é o `atualizado_em`.
- `schema.sql`, linhas 8-16: `pagamento` não tem UNIQUE em `evento_id` e não guarda `atualizado_em`. No teste, o Postgres aceitou as duas versões de `ev-001` e as duas linhas de `ev-002`.
- `ENUNCIADO.md`, passos 1 e 2 (linhas 15-16): o arquivo traz os últimos 7 dias e chega todo dia, e o operador roda o script de novo com o mesmo arquivo quando a importação falha. Um mesmo evento pode chegar em até 7 arquivos seguidos e ser somado outra vez a cada reexecução.

**Impacto**

Somando as quatro linhas, `0012345-10.2019.8.26.0053` fica com R$ 35.501,00 pagos. Os dados sustentam R$ 18.000,50 (15.500,00 da versão corrigida mais 2.500,50 uma única vez). O excesso é de R$ 17.500,50 num precatório de R$ 45.000,00. Se o texto `"2.500,50"` for rejeitado (item 7), a soma cai para R$ 30.500,00, ainda R$ 12.499,50 acima. E o erro cresce a cada arquivo diário e a cada reexecução.

**Causa ou consequência**

Causa do total pago inflado, que é a queixa da operação. Nasce de o passo 2 somar valores em vez de guardar eventos, de o banco não impedir repetição e de a documentação dizer que `evento_id` é único (11).

## 2. Estorno é somado como pagamento

**Evidência**

- `pagamentos.json`: `ev-006` (linhas 50-57) é um pagamento de 5.000 em 2025-02-20; `ev-007` (linhas 58-65) é `"tipo": "estorno"` (linha 63), de 5.000 em 2025-02-21. Os dois são do processo `0034567-32.2018.8.26.0405`.
- `DOCUMENTACAO_TRIBUNAL.md`, linha 15: `tipo` é "sempre 'pagamento'". Já o `schema.sql` prevê `'estorno'` (linha 12) e exige `valor > 0` (linha 13), então o sinal só pode vir do `tipo`.
- O passo 2 do enunciado soma "cada valor" e não menciona `tipo`.
- `ev-009` (linha 85) é uma segunda forma de estorno: `tipo` "pagamento" com `valor` -200. O arquivo usa duas convenções para a mesma coisa.
- Nenhum campo diz qual pagamento foi estornado. A ligação entre `ev-006` e `ev-007` só se deduz por processo, valor e data.

**Impacto**

O processo aparece com R$ 10.000,00 pagos, 80% dos R$ 12.500,00 de valor de face, quando o líquido é zero: pagou num dia e estornou no seguinte. A operação vê como quase quitado um precatório que não recebeu nada.

**Causa ou consequência**

Consequência da mesma raiz do item 1 (somar sem olhar o evento) e do item 11 (a documentação diz que estorno não existe, então ninguém tratou).

## 3. Eventos que o banco rejeita somem sem aviso

**Evidência**

- `ENUNCIADO.md`, passo 5 (linha 19): "o script ignora e segue. Ninguém é avisado."
- Quatro eventos do arquivo não passam no `schema.sql`. Três foram testados: `ev-004` (linha 37, `valor` null, viola NOT NULL), `ev-009` (linha 85, -200, viola `CHECK (valor > 0)`) e `ev-002` (linhas 13 e 29, `valor` em texto, não é numérico). O quarto, `ev-010` (linha 92, processo vazio), não tem como achar um `precatorio_id`, que é obrigatório.

**Impacto**

Deixam de entrar R$ 750,00 (`ev-010`) e R$ 2.500,50 (`ev-002`), mais um pagamento de valor desconhecido (`ev-004`) e um ajuste de -200 (`ev-009`). Pior que o valor é a falta de rastro: quando a conta não fecha com a do tribunal, não existe lista do que ficou de fora. É por isso que ninguém consegue dizer onde nem por quê.

**Causa ou consequência**

Causa de a divergência ser invisível. Amplifica os itens 6 e 7, porque cada defeito de dado vira uma diferença de valor sem registro. Não deriva de outro item: é uma decisão do script.

## 4. Prazo errado em 2 dos 5 precatórios do hub.csv

Regra (`ENUNCIADO.md`, linha 11): apresentado até 2 de abril, pago até 31/12 do ano seguinte; depois de 2 de abril, até 31/12 do ano subsequente ao seguinte.

**Evidência**

| Processo (linha no hub)                   | `apresentado_em`          | Prazo no hub | Prazo pela regra |
| ----------------------------------------- | ------------------------- | ------------ | ---------------- |
| `0012345-10.2019.8.26.0053` (2)           | 2025-04-02                | 2027-12-31   | 2026-12-31       |
| `0023456-21.2020.8.26.0053` (3)           | 2025-04-03                | 2027-12-31   | 2027-12-31       |
| `0034567-32.2018.8.26.0405` (4)           | 2024-02-29                | 2025-12-31   | 2025-12-31       |
| `0045678-43.2021.5.02.0011` (5)           | 2025-04-02T23:30:00-03:00 | 2026-12-31   | 2026-12-31       |
| `0056789-54.2017.4.03.6100` (6)           | 2025-04-03T01:00:00Z      | 2027-12-31   | 2026-12-31       |
| `0067890-65.2016.8.26.0053` (fora do hub) | 2023-12-31                | n/d          | 2025-12-31       |

- Linha 2: "até 2 de abril" inclui o dia 2, então o prazo é 2026-12-31. O hub tratou o limite como exclusivo e deu 2027-12-31. Esse erro existe em qualquer leitura de fuso.
- Linha 6: `2025-04-03T01:00:00Z` é 22:00 de 02/04 em Brasília (UTC-3). Pela data local o precatório entrou no prazo; o hub leu a data do texto (03/04). A linha 5 mostra o contrário: `2025-04-02T23:30:00-03:00` já é 03/04 em UTC, e ali o hub usou a data local. O mesmo 02/04 deu 2027 na linha 2 e 2026 na linha 5, então não há regra única por trás. Se a data válida fosse a UTC, o segundo erro seria a linha 5; nas duas leituras são dois erros.
- A data de apresentação é a mesma no hub e em `apresentacoes.json` (linhas 4, 8, 12, 16 e 20), então o erro está no cálculo, não na entrada. `apresentado_em` tem três formatos nos dois arquivos (data, data-hora com offset e data-hora com `Z`), e o `schema.sql` não tem coluna para a data de apresentação nem para o prazo.
- `0067890-65.2016.8.26.0053` está em `apresentacoes.json` (linha 24) e não está no hub.

**Impacto**

Dois precatórios (`0012345` e `0056789`) aparecem com prazo um ano mais longo que o devido. Juntos valem R$ 67.000,00 dos R$ 120.300,00 de valor de face do hub (56%). A equipe prioriza a carteira por esse prazo, então eles caem um ano na fila. O terceiro (`0067890`, prazo real em 2025-12-31) nem aparece na carteira.

**Causa ou consequência**

Problema próprio, na regra de cálculo (limite e fuso). O formato misto de `apresentado_em` é o que abre espaço para o erro de fuso. A ausência de `0067890` vem do item 5.

## 5. `tribunal.csv` e `hub.csv` divergem em valor, ente e cobertura

A comparação abaixo é pelos dígitos do processo. Por texto exato, parte disso não aparece (itens 6 e 9).

**Evidência**

- `0023456-21.2020.8.26.0053`: `valor_face` de 30.000,00 no `tribunal.csv` (linha 3) e 31.000,00 no `hub.csv` (linha 3).
- `0045678-43.2021.5.02.0011`: ente "União" no tribunal (linha 5) e "Município de Santos" no hub (linha 5).
- `0067890-65.2016.8.26.0053` está no tribunal (linha 6, 7.000,00) e não está no hub. Tem o pagamento `ev-011` de 4.000,00 (`pagamentos.json`, linhas 98-105).
- `0056789-54.2017.4.03.6100` está no hub (linha 6, 22.000,00) e não está no tribunal. Tem o `ev-009`. O número tem J=4 e TR=03 (Justiça Federal, TRF-3) e o hub aponta "Estado de São Paulo" como devedor, combinação incomum que merece confirmação.
- Os valores de face somam 120.300,00 no hub e 104.300,00 no tribunal. A diferença de 16.000,00 fecha com +22.000 (só no hub), +1.000 (`0023456`) e -7.000 (só no tribunal).

**Impacto**

O valor de face é a base do percentual pago e do tamanho da carteira, e o ente diz de quem cobrar. O precatório que recebeu R$ 4.000,00 e não existe no sistema deixa o pagamento sem onde entrar (`precatorio_id` é obrigatório) e fora do acompanhamento. O ente trocado leva a cobrança ao devedor errado. O que existe só no hub pode estar na carteira sem respaldo no tribunal.

**Causa ou consequência**

Os quatro casos reais (valor, ente e os dois de cobertura) não vêm de outros itens e dependem de o tribunal dizer qual lado vale. Já `MUNICIPIO DE SAO PAULO` (hub, linha 2) contra "Município de São Paulo" não é divergência, e a diferença de valor de `0023456` fica escondida pelos itens 6 e 9.

## 6. Processo sem forma única, e o banco não comporta o formato CNJ

**Evidência**

- O CNJ formatado tem 25 caracteres e o `schema.sql` (linha 3) define `numero_processo CHAR(20)`. Testado: o `INSERT` de `0012345-10.2019.8.26.0053` falha com `value too long for type character(20)`, e um `CAST` explícito para `char(20)` corta em silêncio para `0012345-10.2019.8.26`.
- A documentação manda o formato CNJ (`DOCUMENTACAO_TRIBUNAL.md`, linhas 12 e 24) e o banco guarda 20 caracteres. Em algum ponto alguém precisa tirar a pontuação, e isso não está escrito em lugar nenhum.
- Formas encontradas: formatado (11 dos 13 registros de `pagamentos.json`), só dígitos (`ev-005`, linha 44, e `hub.csv`, linha 3, `00234562120208260053`, os dois do processo `0023456-21.2020.8.26.0053`) e vazio (`ev-010`, linha 92).

**Impacto**

Quem compara por texto vê o mesmo precatório como dois. O pagamento `ev-005` (R$ 1.200,00) pode não ser atribuído ao processo certo, e `0023456` aparece ao mesmo tempo como "só no tribunal" e "só no hub". Abrir a forma só com dígitos no Excel é pior: o número vira notação científica, perde os zeros à esquerda e os três últimos dígitos (o Excel guarda 15 dígitos significativos), e salvar grava isso por cima. Isso é risco do fluxo, não algo que dê para ver nos arquivos.

**Causa ou consequência**

Causa dos itens 5 (a diferença de valor de `0023456` some) e 9. Consequência de documentação e schema discordarem (11) e de os arquivos não manterem um formato só.

## 7. `valor` fora do formato documentado

**Evidência**

- A documentação pede número com ponto decimal (`DOCUMENTACAO_TRIBUNAL.md`, linha 13). Três eventos fogem disso:
  - `ev-002`: `"2.500,50"` (linhas 13 e 29), texto em formato brasileiro.
  - `ev-004`: `null` (linha 37).
  - `ev-009`: `-200` (linha 85), com `tipo` "pagamento".
- O banco rejeita os três (item 3). Um conserto improvisado erra sem avisar: `float("2.500,50".replace(",", ""))` dá 2.5005, mil vezes menos.

**Impacto**

Os três eventos não entram. Em `ev-004` sabe-se que houve pagamento em 2025-05-03 no processo `0023456`, mas não quanto. `ev-009` pode ser um estorno de 200 codificado do jeito errado ou um erro; sem resposta do tribunal não dá para decidir entre somar, subtrair ou descartar.

**Causa ou consequência**

Consequência de o tribunal não seguir o próprio leiaute (11). Vira perda silenciosa por causa do item 3. O -200 é a segunda convenção de estorno do item 2.

## 8. `data_pagamento` em DD/MM/AAAA vira outro mês no Postgres

**Evidência**

- `ev-002` (linhas 14 e 30) traz `"10/04/2025"`, e a documentação exige AAAA-MM-DD (linha 14). O `atualizado_em` do mesmo registro é 2025-04-10 (linha 16), então a data é 10 de abril.
- O servidor usa `DateStyle = ISO, MDY`. Testado: `'10/04/2025'::date` devolve `2025-10-04`. Com dia acima de 12 (`25/04/2025`) o Postgres dá erro; só a data ambígua passa.

**Impacto**

Hoje o `ev-002` é barrado pelo `valor` (item 7). Quando alguém arrumar o valor e deixar a data como está, o pagamento entra seis meses depois da data real, sem erro. Relatórios por período e a conferência por data com o tribunal passam a errar sem ninguém notar.

**Causa ou consequência**

Consequência de o tribunal fugir do leiaute (11). O que o torna perigoso é o banco aceitar sem reclamar, ao contrário dos itens 3 e 7.

## 9. Conferência manual no Excel por texto exato

**Evidência**

- `ENUNCIADO.md`, passo 3 (linha 17): o operador abre o arquivo no Excel, confere, salva e compara "exatamente como estão escritos".
- Comparando `tribunal.csv` e `hub.csv` por texto, aparecem 6 alertas: 4 processos sem par (2 só no tribunal, 2 só no hub) e 2 entes diferentes. Três são falsos. `0023456` vira "só no tribunal" e "só no hub" por causa do formato (`hub.csv`, linha 3), e `MUNICIPIO DE SAO PAULO` (hub, linha 2) difere de "Município de São Paulo" (tribunal, linha 2) só por caixa e acento. A diferença real de `valor_face` do `0023456` (item 5) não aparece, porque a linha não casa.
- Os nomes das colunas mudam entre os arquivos (`numero_processo` e `ente_devedor` no tribunal, `processo` e `ente` no hub), e `ente_devedor` é `TEXT` livre no schema: não existe cadastro de entes.

**Impacto**

A operação gasta atenção em alertas falsos e deixa passar uma diferença de R$ 1.000,00. Ao salvar no Excel o arquivo do tribunal é regravado (item 10), e depois ninguém consegue provar o que o tribunal de fato enviou.

**Causa ou consequência**

Consequência de 6 (sem forma única de processo) e de 10 (arquivo fora do layout). Causa de o item 5 chegar incompleto à operação.

## 10. `tribunal.csv` fora do layout documentado

**Evidência**

- A documentação diz UTF-8, vírgula e ponto decimal (`DOCUMENTACAO_TRIBUNAL.md`, linhas 20 e 26). O arquivo:
  - está em Windows-1252: o byte `ed` de "Município" (linha 2) não é UTF-8 válido, e lido como UTF-8 o texto vira `Munic�pio`;
  - separa os campos com `;` (linha 1) e usa vírgula decimal: `45.000,00` (linhas 2 a 6).
- Lida como a documentação manda, a linha 2 vira dois campos, `0012345-10.2019.8.26.0053;Município de São Paulo;45.000` e `00`: a vírgula decimal parte o valor.
- Esse conjunto (ANSI, `;`, vírgula decimal) é o que o Excel em português grava ao salvar como CSV. O arquivo que temos parece ser o que o operador salvou, não o que o tribunal enviou (a confirmar). O `hub.csv`, em contraste, é UTF-8 com vírgula e ponto decimal.

**Impacto**

Um leitor feito pela documentação quebra ou lê errado. O pior caso é silencioso: quem tirar a vírgula para "limpar" faz `45.000,00` virar 45,0. Os nomes com acento deixam de bater com os do hub, e a comparação por ente falha.

**Causa ou consequência**

Consequência de o Excel regravar o arquivo (passo 3 do fluxo) e de a documentação não refletir o que chega (11). Causa de parte dos alertas falsos do item 9.

## 11. A documentação do tribunal não descreve os arquivos

**Evidência**

| Campo                           | A documentação diz            | O arquivo mostra                         |
| ------------------------------- | ----------------------------- | ---------------------------------------- |
| `evento_id` (linha 11)          | identificador único           | repete: `ev-001` e `ev-002`              |
| `processo` (linha 12)           | formato CNJ                   | só dígitos (`ev-005`) e vazio (`ev-010`) |
| `valor` (linha 13)              | número, ponto decimal         | texto brasileiro, null e negativo        |
| `data_pagamento` (linha 14)     | AAAA-MM-DD                    | `10/04/2025`                             |
| `tipo` (linha 15)               | sempre "pagamento"            | existe `estorno` (`ev-007`)              |
| `tribunal.csv` (linhas 20 e 26) | UTF-8, vírgula, ponto decimal | Windows-1252, `;`, vírgula decimal       |

O que a documentação também não diz:

- Se o arquivo é janela móvel ou acumulado. As `data_pagamento` vão de 2025-02-20 a 2025-08-10 (171 dias) e o enunciado fala em 7 dias.
- Que `atualizado_em` serve para versionar o evento (caso do `ev-001`) e como um estorno aponta o pagamento original.
- O fuso das datas e quais campos podem vir vazios.
- Nada sobre `apresentacoes.json`, de onde sai a data que gera o prazo.
- A versão 2.1 não tem data nem histórico de mudanças.

**Impacto**

Quem escreve o script confia na documentação. Ninguém tratou estorno nem evento repetido porque o documento diz que isso não acontece, e qualquer leitor escrito pelo leiaute já nasce quebrado. Sem versionamento, o formato muda e ninguém é avisado.

**Causa ou consequência**

Causa dos itens 1, 2, 7, 8 e 10. Em si, consequência de o leiaute não ser mantido junto com o arquivo que o tribunal envia.

## Outras conferências

- `tipo`: aparecem só `pagamento` (12 registros) e `estorno` (1), sem variação de caixa nem espaços, e o `CHECK` do schema aceita os dois. O defeito do `tipo` está nos itens 2 e 11, não no domínio de valores.
- `atualizado_em`: é do registro do evento (a documentação diz "última alteração do registro") e só distingue as duas versões do `ev-001`. Sempre vem em ISO 8601 com `-03:00`.
- Dígitos verificadores do CNJ: nenhum dos 6 processos passa na conta do módulo 97. Os dados são fictícios (o enunciado avisa), então não tratei como erro.
- `2024-02-29` (`apresentacoes.json`, linha 12) é data válida, e o prazo do hub para ela está certo.
- Sem explicação nos dados: o `ev-001` tem `data_pagamento` 2025-03-10, 23 dias antes da apresentação do precatório (2025-04-02). Vai para as dúvidas.

## Como conferi o comportamento do banco

Rodado no Postgres do `docker-compose.yml`, em tabelas temporárias com as colunas do `schema.sql`. As tabelas reais não foram tocadas.

```sql
SHOW datestyle;                                  -- ISO, MDY
SELECT '10/04/2025'::date;                       -- 2025-10-04
SELECT '25/04/2025'::date;                       -- erro: fora do intervalo

CREATE TEMP TABLE t_prec (numero_processo CHAR(20) NOT NULL UNIQUE);
INSERT INTO t_prec VALUES ('0012345-10.2019.8.26.0053');  -- erro: value too long for type character(20)
SELECT '0012345-10.2019.8.26.0053'::char(20);             -- 0012345-10.2019.8.26 (corta sem erro)

CREATE TEMP TABLE t_pag (
  evento_id TEXT NOT NULL,
  tipo      TEXT NOT NULL CHECK (tipo IN ('pagamento', 'estorno')),
  valor     NUMERIC(15,2) NOT NULL CHECK (valor > 0),
  pago_em   DATE NOT NULL
);
INSERT INTO t_pag VALUES ('ev-004', 'pagamento', NULL, '2025-05-03');        -- erro: NOT NULL
INSERT INTO t_pag VALUES ('ev-009', 'pagamento', -200, '2025-07-20');        -- erro: CHECK
INSERT INTO t_pag VALUES ('ev-002', 'pagamento', '2.500,50', '2025-04-10');  -- erro: numeric inválido
INSERT INTO t_pag VALUES ('ev-001', 'pagamento', 15000, '2025-03-10'),
                         ('ev-001', 'pagamento', 15500, '2025-03-10');       -- aceita as duas
```

# Dúvidas antes de pôr a limpeza em produção

Cada pergunta traz o que o código assume hoje. Se a resposta for outra, é isso que precisa mudar. A ordem é pelo efeito nos valores e prazos. Os itens citados são os do [DIAGNOSTICO.md](DIAGNOSTICO.md).

## Para o tribunal

1. **`atualizado_em` define a versão que vale?** O `ev-001` veio com 15.000 e depois com 15.500.
   Hoje: vale a mais recente.
2. **Como um estorno é informado?** O `ev-007` usa `tipo` "estorno"; o `ev-009` usa "pagamento" com -200. Dá para enviar o `evento_id` do pagamento estornado?
   Hoje: `estorno` subtrai, o `ev-009` fica fora e o `ev-007` não é ligado a um pagamento específico.
3. **Quais os dados corretos destes eventos?**
   - `ev-004`: qual o valor do pagamento de 03/05/2025 no processo `0023456`?
   - `ev-009`: os -200 são estorno, ajuste ou erro?
   - `ev-010`: de qual processo são os 750,00?

   Hoje: os três ficam fora do total.
4. **O arquivo diário traz mesmo os últimos 7 dias?** O exemplo vai de 20/02 a 10/08/2025. Um evento pode ser cancelado simplesmente deixando de aparecer?
   Hoje: nada é removido por ausência.
5. **Qual data e fuso valem para a apresentação?** `2025-04-03T01:00:00Z` é 02/04 em Brasília, e a diferença muda o prazo do `0056789` em um ano.
   Hoje: data de Brasília, prazo em 31/12/2026.
6. **Qual o valor de face do `0023456`: 30.000,00 ou 31.000,00?** A diferença pode ser erro ou atualização monetária.
   Hoje: 30.000,00, o do tribunal.
7. **Quem é o ente devedor do `0045678`: União ou Município de Santos?**
   Hoje: União.
8. **O `0056789` existe?** Está no hub e não na lista do tribunal, e o hub aponta o Estado de São Paulo em um processo da Justiça Federal. A lista semanal é completa ou só traz mudanças?
   Hoje: mantido com os dados do hub, marcado como dúvida.
9. **O `ev-001` foi pago em 10/03/2025, antes da apresentação em 02/04/2025. Qual das datas está errada, se alguma?**
   Hoje: o pagamento conta, marcado como dúvida.
10. **`10/04/2025` é 10 de abril? O formato brasileiro vai continuar aparecendo?** Vale o mesmo para valores como `2.500,50` (itens 7 e 8).
    Hoje: dia/mês/ano e vírgula decimal.
11. **O `tribunal.csv` sai de vocês em Windows-1252 com `;`, ou como diz a documentação?** (item 10)
    Hoje: os dois formatos são aceitos.

## Para a operação

1. **Os totais que estão hoje no sistema já foram inflados?** Quantas vezes cada arquivo foi importado ou reexecutado? Existem os arquivos antigos guardados?
   Importa porque: a limpeza parte só do arquivo atual e não corrige o histórico.
2. **Onde fica o total pago hoje, e o que o script atual faz com um evento ruim?** O `schema.sql` não tem essa coluna e o script não está no repositório.
   Importa porque: sem isso não dá para planejar a troca.
3. **Quando tribunal e hub divergem, quem decide e qual lado vale?** Alguém edita o hub à mão?
   Hoje: vale o tribunal, o que poderia apagar uma correção manual.
4. **O anexo original do tribunal é guardado?** O arquivo que recebemos parece ter sido salvo pelo Excel.
   Importa porque: se o Excel mudou algum valor, a base herdou.
5. **De onde vem o `apresentacoes.json` e como o hub calcula o prazo?** Há dois prazos errados.
   Hoje: o prazo é recalculado a partir desse arquivo.
6. **Alguma decisão já foi tomada com os prazos ou totais errados?** `0012345` e `0056789` aparecem com um ano a mais.
   Importa porque: pode haver ação urgente antes da correção da base.
7. **Quem recebe as pendências e em quanto tempo precisa resolvê-las?**
   Hoje: elas só aparecem no relatório e no terminal.
8. **Um precatório ou pagamento marcado como dúvida pode ser usado nos relatórios?**
   Hoje: sim. No schema original a marca nem chega ao banco.

## O que eu não publicaria sem resposta

As perguntas 1 a 3 do tribunal e 1 da operação mudam o total pago. A 5 muda prazo. Sem elas, a base serve para conferência, não como fonte oficial.

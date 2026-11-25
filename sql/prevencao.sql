-- Migração sobre o schema.sql, para aplicar em uma base já limpa.
-- Roda em uma transação: se uma linha atual violar uma regra, nada muda.
BEGIN;

-- Ente com uma grafia só (diagnóstico 9)
CREATE TABLE ente (nome TEXT PRIMARY KEY);
INSERT INTO ente SELECT DISTINCT ente_devedor FROM precatorio;

-- Precatório: chave só com dígitos (6), prazo calculado pelo banco (4), dúvida visível (5)
ALTER TABLE precatorio
    ADD CONSTRAINT precatorio_processo_20_digitos CHECK (numero_processo ~ '^[0-9]{20}$'),
    ADD CONSTRAINT precatorio_ente_fk FOREIGN KEY (ente_devedor) REFERENCES ente (nome),
    ADD CONSTRAINT precatorio_valor_face_positivo CHECK (valor_face > 0),
    ADD COLUMN situacao TEXT NOT NULL DEFAULT 'ok' CHECK (situacao IN ('ok', 'duvida')),
    -- data já convertida para Brasília pelo importador
    ADD COLUMN apresentado_em DATE,
    ADD COLUMN prazo_pagamento DATE GENERATED ALWAYS AS (
        make_date(
            EXTRACT(YEAR FROM apresentado_em)::int
                + CASE WHEN (EXTRACT(MONTH FROM apresentado_em), EXTRACT(DAY FROM apresentado_em)) <= (4, 2)
                       THEN 1 ELSE 2 END,
            12, 31)
    ) STORED;

-- Pagamento: uma linha por evento, com a versão (1)
-- Linhas antigas recebem 'epoch', então qualquer versão real as substitui.
ALTER TABLE pagamento ADD COLUMN atualizado_em TIMESTAMPTZ NOT NULL DEFAULT 'epoch';
ALTER TABLE pagamento ALTER COLUMN atualizado_em DROP DEFAULT;
ALTER TABLE pagamento ADD CONSTRAINT pagamento_evento_unico UNIQUE (evento_id);

-- Rastro de tudo o que chega, inclusive o rejeitado (3)
CREATE TABLE importacao (
    id          BIGSERIAL PRIMARY KEY,
    arquivo     TEXT        NOT NULL,
    sha256      CHAR(64)    NOT NULL,
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evento_recebido (
    id            BIGSERIAL PRIMARY KEY,
    importacao_id BIGINT      NOT NULL REFERENCES importacao (id),
    evento_id     TEXT,                 -- sem NOT NULL: o registro ruim também é guardado
    atualizado_em TIMESTAMPTZ,
    conteudo      JSONB       NOT NULL, -- como veio no arquivo
    erro          TEXT,                 -- NULL = aceito
    resolvido_em  TIMESTAMPTZ
);
CREATE INDEX ON evento_recebido (evento_id, atualizado_em);

CREATE VIEW pendencia AS
SELECT r.id, i.arquivo, i.recebido_em, r.evento_id, r.erro, r.conteudo
FROM evento_recebido r
JOIN importacao i ON i.id = r.importacao_id
WHERE r.erro IS NOT NULL AND r.resolvido_em IS NULL;

-- Total pago sempre derivado dos eventos, nunca acumulado em coluna (1, 2)
CREATE VIEW total_pago AS
SELECT p.id AS precatorio_id,
       p.numero_processo,
       COALESCE(SUM(CASE g.tipo WHEN 'estorno' THEN -g.valor ELSE g.valor END), 0) AS total
FROM precatorio p
LEFT JOIN pagamento g ON g.precatorio_id = p.id
GROUP BY p.id;

COMMIT;

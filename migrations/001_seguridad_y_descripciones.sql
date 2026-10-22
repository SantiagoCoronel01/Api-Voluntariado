-- Execute on the selected application database AFTER taking a backup.
-- MySQL DDL commits implicitly. This file does not modify account states.
ALTER TABLE usuario MODIFY COLUMN clave VARCHAR(255) NOT NULL;
ALTER TABLE usuario MODIFY COLUMN mail VARCHAR(254) NOT NULL;
ALTER TABLE anuncios MODIFY COLUMN titulo VARCHAR(150) CHARACTER SET utf8mb4 NOT NULL;
ALTER TABLE anuncios MODIFY COLUMN descripcion TEXT CHARACTER SET utf8mb4 NOT NULL;

CREATE TABLE IF NOT EXISTS sesiones_usuario (
    token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    idusuario INT NOT NULL,
    creada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira DATETIME NOT NULL,
    revocada TINYINT NOT NULL DEFAULT 0,
    INDEX sesiones_por_usuario (idusuario, revocada),
    INDEX sesiones_por_expiracion (expira)
) ENGINE=InnoDB;

-- Idempotency records are scoped to an authenticated actor and an operation.
CREATE TABLE IF NOT EXISTS operaciones_idempotentes (
    idusuario INT NOT NULL,
    operacion VARCHAR(40) NOT NULL,
    clave VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_hash CHAR(64) CHARACTER SET ascii NOT NULL,
    resultado LONGTEXT NULL,
    estado_http SMALLINT NULL,
    creada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (idusuario, operacion, clave)
) ENGINE=InnoDB;

-- StockLedger — full schema
-- Run once to set up the database.

CREATE DATABASE IF NOT EXISTS inventory_db;
USE inventory_db;

-- Users
CREATE TABLE IF NOT EXISTS users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    username   VARCHAR(50)  UNIQUE NOT NULL,
    password   VARCHAR(255) NOT NULL,          -- bcrypt hash, never plain text
    role       ENUM('admin','manager','staff') NOT NULL DEFAULT 'staff',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100)   NOT NULL,
    category       VARCHAR(50)    NOT NULL,
    unit           VARCHAR(20)    NOT NULL,     -- display unit  (Kg / Litre / Piece …)
    unit_type      VARCHAR(20)    NOT NULL DEFAULT 'piece',  -- internal type (kg/litre/piece/gram)
    net_weight     DECIMAL(10,2)  NOT NULL DEFAULT 0,
    quantity       DECIMAL(10,2)  NOT NULL DEFAULT 0,
    min_stock      INT            NOT NULL DEFAULT 5,
    purchase_price DECIMAL(10,2)  NOT NULL DEFAULT 0,
    selling_price  DECIMAL(10,2)  NOT NULL DEFAULT 0,
    created_at     DATETIME       DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Sales
CREATE TABLE IF NOT EXISTS sales (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    product_id    INT            NOT NULL,
    quantity_sold DECIMAL(10,2)  NOT NULL,
    amount        DECIMAL(10,2)  NOT NULL,
    profit        DECIMAL(10,2)  NOT NULL,
    created_at    DATETIME       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

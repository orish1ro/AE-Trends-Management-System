-- AE Trends database (SQLite) - built from the FINAL completed ERD
PRAGMA foreign_keys = ON;

-- ============================================================
-- CUSTOMER
-- ============================================================
CREATE TABLE IF NOT EXISTS Customer (
    CustomerID     INTEGER PRIMARY KEY AUTOINCREMENT,
    FullName       TEXT NOT NULL,
    ContactNumber  TEXT,
    Address        TEXT
);

-- ============================================================
-- PLATFORM  (Walk-in, TikTok Live, Facebook Live, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS Platform (
    PlatformID     INTEGER PRIMARY KEY AUTOINCREMENT,
    PlatformName   TEXT NOT NULL UNIQUE
);

-- ============================================================
-- STAFF  (also holds login credentials — Owner, Cashier, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS Staff (
    StaffID        INTEGER PRIMARY KEY AUTOINCREMENT,
    Name           TEXT NOT NULL,
    Role           TEXT NOT NULL DEFAULT 'Cashier'
                   CHECK (Role IN ('Owner','Cashier','Inventory Staff')),
    ContactNumber  TEXT,
    Username       TEXT NOT NULL UNIQUE,
    PasswordHash   TEXT NOT NULL
);

-- ============================================================
-- SUPPLIER
-- ============================================================
CREATE TABLE IF NOT EXISTS Supplier (
    SupplierID     INTEGER PRIMARY KEY AUTOINCREMENT,
    SupplierName   TEXT NOT NULL,
    Location       TEXT,
    ContactNumber  TEXT
);

-- ============================================================
-- PRODUCT
-- ============================================================
CREATE TABLE IF NOT EXISTS Product (
    ProductID      INTEGER PRIMARY KEY AUTOINCREMENT,
    SupplierID     INTEGER NOT NULL,
    StaffID        INTEGER NOT NULL,
    ProductName    TEXT NOT NULL,
    Category       TEXT,
    Price          REAL NOT NULL CHECK (Price >= 0),
    StockQuantity  INTEGER NOT NULL DEFAULT 0 CHECK (StockQuantity >= 0),
    DateAdded      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ExpirationDate TEXT,
    LastEditedAt   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (SupplierID) REFERENCES Supplier(SupplierID),
    FOREIGN KEY (StaffID)    REFERENCES Staff(StaffID)
);

-- ============================================================
-- ORDERS
-- ============================================================
CREATE TABLE IF NOT EXISTS Orders (
    OrderID          INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerID       INTEGER NOT NULL,
    StaffID          INTEGER NOT NULL,
    PlatformID       INTEGER NOT NULL,
    OrderDate        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    TotalAmount      REAL NOT NULL DEFAULT 0 CHECK (TotalAmount >= 0),
    OrderStatus      TEXT NOT NULL DEFAULT 'Pending'
                     CHECK (OrderStatus IN ('Pending','Paid','Prepared','Shipped','Completed','Refunded','Cancelled')),
    DeliveryAddress  TEXT,
    FOREIGN KEY (CustomerID) REFERENCES Customer(CustomerID),
    FOREIGN KEY (StaffID)    REFERENCES Staff(StaffID),
    FOREIGN KEY (PlatformID) REFERENCES Platform(PlatformID)
);

-- ============================================================
-- ORDER DETAILS
-- ============================================================
CREATE TABLE IF NOT EXISTS OrderDetails (
    OrderDetailsID   INTEGER PRIMARY KEY AUTOINCREMENT,
    OrderID          INTEGER NOT NULL,
    ProductID        INTEGER NOT NULL,
    Quantity         INTEGER NOT NULL CHECK (Quantity > 0),
    UnitPriceAtOrder REAL NOT NULL CHECK (UnitPriceAtOrder >= 0),
    Subtotal         REAL NOT NULL CHECK (Subtotal >= 0),
    FOREIGN KEY (OrderID)   REFERENCES Orders(OrderID) ON DELETE CASCADE,
    FOREIGN KEY (ProductID) REFERENCES Product(ProductID)
);

-- ============================================================
-- PAYMENT
-- ============================================================
CREATE TABLE IF NOT EXISTS Payment (
    PaymentID       INTEGER PRIMARY KEY AUTOINCREMENT,
    OrderID         INTEGER NOT NULL UNIQUE,
    PaymentMethod   TEXT,
    AmountPaid      REAL NOT NULL DEFAULT 0 CHECK (AmountPaid >= 0),
    PaymentDate     TEXT DEFAULT (datetime('now','localtime')),
    PaymentStatus   TEXT NOT NULL DEFAULT 'Unpaid'
                    CHECK (PaymentStatus IN ('Unpaid','Paid','Refunded')),
    ReferenceNumber TEXT,
    ReceiptImageURL TEXT,
    FOREIGN KEY (OrderID) REFERENCES Orders(OrderID) ON DELETE CASCADE
);

-- ============================================================
-- PURCHASE ORDER
-- ============================================================
CREATE TABLE IF NOT EXISTS PurchaseOrder (
    PurchaseOrderID      INTEGER PRIMARY KEY AUTOINCREMENT,
    StaffID              INTEGER NOT NULL,
    SupplierID           INTEGER NOT NULL,
    OrderDate            TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ExpectedDeliveryDate TEXT,
    Status               TEXT NOT NULL DEFAULT 'Pending'
                         CHECK (Status IN ('Pending','Received','Cancelled')),
    TotalCost            REAL NOT NULL DEFAULT 0 CHECK (TotalCost >= 0),
    FOREIGN KEY (StaffID)    REFERENCES Staff(StaffID),
    FOREIGN KEY (SupplierID) REFERENCES Supplier(SupplierID)
);

-- ============================================================
-- PURCHASE ORDER DETAILS
-- ============================================================
CREATE TABLE IF NOT EXISTS PurchaseOrderDetails (
    PODetailsID      INTEGER PRIMARY KEY AUTOINCREMENT,
    PurchaseOrderID  INTEGER NOT NULL,
    ProductID        INTEGER NOT NULL,
    Quantity         INTEGER NOT NULL CHECK (Quantity > 0),
    UnitCost         REAL NOT NULL CHECK (UnitCost >= 0),
    UnitSize         REAL,
    UnitMeasure      TEXT,
    FOREIGN KEY (PurchaseOrderID) REFERENCES PurchaseOrder(PurchaseOrderID) ON DELETE CASCADE,
    FOREIGN KEY (ProductID)       REFERENCES Product(ProductID)
);

-- ============================================================
-- SEED DATA — Platforms (Only insert if empty)
-- ============================================================
INSERT OR IGNORE INTO Platform (PlatformName) VALUES
('Walk-in'),
('Shopee'),
('TikTok Shop'),
('Lazada'),
('Facebook Live');

-- ============================================================
-- BANK  (banks offered under "Online Banking"; new ones are added from the app)
-- ============================================================
CREATE TABLE IF NOT EXISTS Bank (
    BankID    INTEGER PRIMARY KEY AUTOINCREMENT,
    BankName  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

INSERT OR IGNORE INTO Bank (BankName) VALUES
('MariBank'),
('BPI'),
('GoTyme');

-- ============================================================
-- CATEGORY  (product categories; the owner can add and remove unused ones)
-- ============================================================
CREATE TABLE IF NOT EXISTS Category (
    CategoryID    INTEGER PRIMARY KEY AUTOINCREMENT,
    CategoryName  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

INSERT OR IGNORE INTO Category (CategoryName) VALUES
('Clothing • Tops'),
('Clothing • Bottoms'),
('Clothing • Outerwear'),
('Skincare • Face'),
('Skincare • Treatment');

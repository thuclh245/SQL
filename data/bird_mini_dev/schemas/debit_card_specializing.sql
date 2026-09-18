-- Database: debit_card_specializing

CREATE TABLE "customers" (
    "CustomerID" integer PRIMARY KEY,
    "Segment" text,
    "Currency" text
);

CREATE TABLE "gasstations" (
    "GasStationID" integer PRIMARY KEY,
    "ChainID" integer,
    "Country" text,
    "Segment" text
);

CREATE TABLE "products" (
    "ProductID" integer PRIMARY KEY,
    "Description" text
);

CREATE TABLE "transactions_1k" (
    "TransactionID" integer PRIMARY KEY,
    "Date" date,
    "Time" text,
    "CustomerID" integer,
    "CardID" integer,
    "GasStationID" integer,
    "ProductID" integer,
    "Amount" integer,
    "Price" real
);

CREATE TABLE "yearmonth" (
    "CustomerID" integer,
    "Date" text,
    "Consumption" real,
    FOREIGN KEY ("CustomerID") REFERENCES "customers" ("CustomerID")
);

-- Database: financial

CREATE TABLE "account" (
    "account_id" integer PRIMARY KEY,
    "district_id" integer,
    "frequency" text,
    "date" date,
    FOREIGN KEY ("district_id") REFERENCES "district" ("district_id")
);

CREATE TABLE "card" (
    "card_id" integer PRIMARY KEY,
    "disp_id" integer,
    "type" text,
    "issued" date,
    FOREIGN KEY ("disp_id") REFERENCES "disp" ("disp_id")
);

CREATE TABLE "client" (
    "client_id" integer PRIMARY KEY,
    "gender" text,
    "birth_date" date,
    "district_id" integer,
    FOREIGN KEY ("district_id") REFERENCES "district" ("district_id")
);

CREATE TABLE "disp" (
    "disp_id" integer PRIMARY KEY,
    "client_id" integer,
    "account_id" integer,
    "type" text,
    FOREIGN KEY ("client_id") REFERENCES "client" ("client_id"),
    FOREIGN KEY ("account_id") REFERENCES "account" ("account_id")
);

CREATE TABLE "district" (
    "district_id" integer PRIMARY KEY,
    "A2" text,
    "A3" text,
    "A4" text,
    "A5" text,
    "A6" text,
    "A7" text,
    "A8" integer,
    "A9" integer,
    "A10" real,
    "A11" integer,
    "A12" real,
    "A13" real,
    "A14" integer,
    "A15" integer,
    "A16" integer
);

CREATE TABLE "loan" (
    "loan_id" integer PRIMARY KEY,
    "account_id" integer,
    "date" date,
    "amount" integer,
    "duration" integer,
    "payments" real,
    "status" text,
    FOREIGN KEY ("account_id") REFERENCES "account" ("account_id")
);

CREATE TABLE "order" (
    "order_id" integer PRIMARY KEY,
    "account_id" integer,
    "bank_to" text,
    "account_to" integer,
    "amount" real,
    "k_symbol" text,
    FOREIGN KEY ("account_id") REFERENCES "account" ("account_id")
);

CREATE TABLE "trans" (
    "trans_id" integer PRIMARY KEY,
    "account_id" integer,
    "date" date,
    "type" text,
    "operation" text,
    "amount" integer,
    "balance" integer,
    "k_symbol" text,
    "bank" text,
    "account" integer,
    FOREIGN KEY ("account_id") REFERENCES "account" ("account_id")
);

-- Database: toxicology

CREATE TABLE "atom" (
    "atom_id" text PRIMARY KEY,
    "molecule_id" text,
    "element" text,
    FOREIGN KEY ("molecule_id") REFERENCES "molecule" ("molecule_id")
);

CREATE TABLE "bond" (
    "bond_id" text PRIMARY KEY,
    "molecule_id" text,
    "bond_type" text,
    FOREIGN KEY ("molecule_id") REFERENCES "molecule" ("molecule_id")
);

CREATE TABLE "connected" (
    "atom_id" text,
    "atom_id2" text,
    "bond_id" text,
    FOREIGN KEY ("bond_id") REFERENCES "bond" ("bond_id"),
    FOREIGN KEY ("atom_id2") REFERENCES "atom" ("atom_id"),
    FOREIGN KEY ("atom_id") REFERENCES "atom" ("atom_id")
);

CREATE TABLE "molecule" (
    "molecule_id" text PRIMARY KEY,
    "label" text
);

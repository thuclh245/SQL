-- Database: superhero

CREATE TABLE "alignment" (
    "id" integer PRIMARY KEY,
    "alignment" text
);

CREATE TABLE "attribute" (
    "id" integer PRIMARY KEY,
    "attribute_name" text
);

CREATE TABLE "colour" (
    "id" integer PRIMARY KEY,
    "colour" text
);

CREATE TABLE "gender" (
    "id" integer PRIMARY KEY,
    "gender" text
);

CREATE TABLE "publisher" (
    "id" integer PRIMARY KEY,
    "publisher_name" text
);

CREATE TABLE "race" (
    "id" integer PRIMARY KEY,
    "race" text
);

CREATE TABLE "superhero" (
    "id" integer PRIMARY KEY,
    "superhero_name" text,
    "full_name" text,
    "gender_id" integer,
    "eye_colour_id" integer,
    "hair_colour_id" integer,
    "skin_colour_id" integer,
    "race_id" integer,
    "publisher_id" integer,
    "alignment_id" integer,
    "height_cm" integer,
    "weight_kg" integer,
    FOREIGN KEY ("skin_colour_id") REFERENCES "colour" ("id"),
    FOREIGN KEY ("race_id") REFERENCES "race" ("id"),
    FOREIGN KEY ("publisher_id") REFERENCES "publisher" ("id"),
    FOREIGN KEY ("hair_colour_id") REFERENCES "colour" ("id"),
    FOREIGN KEY ("gender_id") REFERENCES "gender" ("id"),
    FOREIGN KEY ("eye_colour_id") REFERENCES "colour" ("id"),
    FOREIGN KEY ("alignment_id") REFERENCES "alignment" ("id")
);

CREATE TABLE "hero_attribute" (
    "hero_id" integer,
    "attribute_id" integer,
    "attribute_value" integer,
    FOREIGN KEY ("hero_id") REFERENCES "superhero" ("id"),
    FOREIGN KEY ("attribute_id") REFERENCES "attribute" ("id")
);

CREATE TABLE "superpower" (
    "id" integer PRIMARY KEY,
    "power_name" text
);

CREATE TABLE "hero_power" (
    "hero_id" integer,
    "power_id" integer,
    FOREIGN KEY ("power_id") REFERENCES "superpower" ("id"),
    FOREIGN KEY ("hero_id") REFERENCES "superhero" ("id")
);

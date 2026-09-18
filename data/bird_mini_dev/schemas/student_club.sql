-- Database: student_club

CREATE TABLE "event" (
    "event_id" text PRIMARY KEY,
    "event_name" text,
    "event_date" text,
    "type" text,
    "notes" text,
    "location" text,
    "status" text
);

CREATE TABLE "major" (
    "major_id" text PRIMARY KEY,
    "major_name" text,
    "department" text,
    "college" text
);

CREATE TABLE "zip_code" (
    "zip_code" integer PRIMARY KEY,
    "type" text,
    "city" text,
    "county" text,
    "state" text,
    "short_state" text
);

CREATE TABLE "attendance" (
    "link_to_event" text,
    "link_to_member" text,
    FOREIGN KEY ("link_to_member") REFERENCES "member" ("member_id"),
    FOREIGN KEY ("link_to_event") REFERENCES "event" ("event_id")
);

CREATE TABLE "budget" (
    "budget_id" text PRIMARY KEY,
    "category" text,
    "spent" real,
    "remaining" real,
    "amount" integer,
    "event_status" text,
    "link_to_event" text,
    FOREIGN KEY ("link_to_event") REFERENCES "event" ("event_id")
);

CREATE TABLE "expense" (
    "expense_id" text PRIMARY KEY,
    "expense_description" text,
    "expense_date" text,
    "cost" real,
    "approved" text,
    "link_to_member" text,
    "link_to_budget" text,
    FOREIGN KEY ("link_to_member") REFERENCES "member" ("member_id"),
    FOREIGN KEY ("link_to_budget") REFERENCES "budget" ("budget_id")
);

CREATE TABLE "income" (
    "income_id" text PRIMARY KEY,
    "date_received" text,
    "amount" integer,
    "source" text,
    "notes" text,
    "link_to_member" text,
    FOREIGN KEY ("link_to_member") REFERENCES "member" ("member_id")
);

CREATE TABLE "member" (
    "member_id" text PRIMARY KEY,
    "first_name" text,
    "last_name" text,
    "email" text,
    "position" text,
    "t_shirt_size" text,
    "phone" text,
    "zip" integer,
    "link_to_major" text,
    FOREIGN KEY ("zip") REFERENCES "zip_code" ("zip_code"),
    FOREIGN KEY ("link_to_major") REFERENCES "major" ("major_id")
);

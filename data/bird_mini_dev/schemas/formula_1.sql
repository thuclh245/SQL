-- Database: formula_1

CREATE TABLE "circuits" (
    "circuitId" integer PRIMARY KEY,
    "circuitRef" text,
    "name" text,
    "location" text,
    "country" text,
    "lat" real,
    "lng" real,
    "alt" integer,
    "url" text
);

CREATE TABLE "constructors" (
    "constructorId" integer PRIMARY KEY,
    "constructorRef" text,
    "name" text,
    "nationality" text,
    "url" text
);

CREATE TABLE "drivers" (
    "driverId" integer PRIMARY KEY,
    "driverRef" text,
    "number" integer,
    "code" text,
    "forename" text,
    "surname" text,
    "dob" date,
    "nationality" text,
    "url" text
);

CREATE TABLE "seasons" (
    "year" integer PRIMARY KEY,
    "url" text
);

CREATE TABLE "races" (
    "raceId" integer PRIMARY KEY,
    "year" integer,
    "round" integer,
    "circuitId" integer,
    "name" text,
    "date" date,
    "time" text,
    "url" text,
    FOREIGN KEY ("circuitId") REFERENCES "circuits" ("circuitId"),
    FOREIGN KEY ("year") REFERENCES "seasons" ("year")
);

CREATE TABLE "constructorResults" (
    "constructorResultsId" integer PRIMARY KEY,
    "raceId" integer,
    "constructorId" integer,
    "points" real,
    "status" text,
    FOREIGN KEY ("constructorId") REFERENCES "constructors" ("constructorId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

CREATE TABLE "constructorStandings" (
    "constructorStandingsId" integer PRIMARY KEY,
    "raceId" integer,
    "constructorId" integer,
    "points" real,
    "position" integer,
    "positionText" text,
    "wins" integer,
    FOREIGN KEY ("constructorId") REFERENCES "constructors" ("constructorId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

CREATE TABLE "driverStandings" (
    "driverStandingsId" integer PRIMARY KEY,
    "raceId" integer,
    "driverId" integer,
    "points" real,
    "position" integer,
    "positionText" text,
    "wins" integer,
    FOREIGN KEY ("driverId") REFERENCES "drivers" ("driverId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

CREATE TABLE "lapTimes" (
    "raceId" integer,
    "driverId" integer,
    "lap" integer,
    "position" integer,
    "time" text,
    "milliseconds" integer,
    FOREIGN KEY ("driverId") REFERENCES "drivers" ("driverId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

CREATE TABLE "pitStops" (
    "raceId" integer,
    "driverId" integer,
    "stop" integer,
    "lap" integer,
    "time" text,
    "duration" text,
    "milliseconds" integer,
    FOREIGN KEY ("driverId") REFERENCES "drivers" ("driverId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

CREATE TABLE "qualifying" (
    "qualifyId" integer PRIMARY KEY,
    "raceId" integer,
    "driverId" integer,
    "constructorId" integer,
    "number" integer,
    "position" integer,
    "q1" text,
    "q2" text,
    "q3" text,
    FOREIGN KEY ("constructorId") REFERENCES "constructors" ("constructorId"),
    FOREIGN KEY ("driverId") REFERENCES "drivers" ("driverId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

CREATE TABLE "status" (
    "statusId" integer PRIMARY KEY,
    "status" text
);

CREATE TABLE "results" (
    "resultId" integer PRIMARY KEY,
    "raceId" integer,
    "driverId" integer,
    "constructorId" integer,
    "number" integer,
    "grid" integer,
    "position" integer,
    "positionText" text,
    "positionOrder" integer,
    "points" real,
    "laps" integer,
    "time" text,
    "milliseconds" integer,
    "fastestLap" integer,
    "rank" integer,
    "fastestLapTime" text,
    "fastestLapSpeed" text,
    "statusId" integer,
    FOREIGN KEY ("statusId") REFERENCES "status" ("statusId"),
    FOREIGN KEY ("constructorId") REFERENCES "constructors" ("constructorId"),
    FOREIGN KEY ("driverId") REFERENCES "drivers" ("driverId"),
    FOREIGN KEY ("raceId") REFERENCES "races" ("raceId")
);

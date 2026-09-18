-- Database: codebase_community

CREATE TABLE "badges" (
    "Id" integer PRIMARY KEY,
    "UserId" integer,
    "Name" text,
    "Date" datetime,
    FOREIGN KEY ("UserId") REFERENCES "users" ("Id")
);

CREATE TABLE "comments" (
    "Id" integer PRIMARY KEY,
    "PostId" integer,
    "Score" integer,
    "Text" text,
    "CreationDate" datetime,
    "UserId" integer,
    "UserDisplayName" text,
    FOREIGN KEY ("UserId") REFERENCES "users" ("Id"),
    FOREIGN KEY ("PostId") REFERENCES "posts" ("Id")
);

CREATE TABLE "postHistory" (
    "Id" integer PRIMARY KEY,
    "PostHistoryTypeId" integer,
    "PostId" integer,
    "RevisionGUID" text,
    "CreationDate" datetime,
    "UserId" integer,
    "Text" text,
    "Comment" text,
    "UserDisplayName" text,
    FOREIGN KEY ("UserId") REFERENCES "users" ("Id"),
    FOREIGN KEY ("PostId") REFERENCES "posts" ("Id")
);

CREATE TABLE "postLinks" (
    "Id" integer PRIMARY KEY,
    "CreationDate" datetime,
    "PostId" integer,
    "RelatedPostId" integer,
    "LinkTypeId" integer,
    FOREIGN KEY ("RelatedPostId") REFERENCES "posts" ("Id"),
    FOREIGN KEY ("PostId") REFERENCES "posts" ("Id")
);

CREATE TABLE "posts" (
    "Id" integer PRIMARY KEY,
    "PostTypeId" integer,
    "AcceptedAnswerId" integer,
    "CreaionDate" datetime,
    "Score" integer,
    "ViewCount" integer,
    "Body" text,
    "OwnerUserId" integer,
    "LasActivityDate" datetime,
    "Title" text,
    "Tags" text,
    "AnswerCount" integer,
    "CommentCount" integer,
    "FavoriteCount" integer,
    "LastEditorUserId" integer,
    "LastEditDate" datetime,
    "CommunityOwnedDate" datetime,
    "ParentId" integer,
    "ClosedDate" datetime,
    "OwnerDisplayName" text,
    "LastEditorDisplayName" text,
    FOREIGN KEY ("ParentId") REFERENCES "posts" ("Id"),
    FOREIGN KEY ("OwnerUserId") REFERENCES "users" ("Id"),
    FOREIGN KEY ("LastEditorUserId") REFERENCES "users" ("Id")
);

CREATE TABLE "tags" (
    "Id" integer PRIMARY KEY,
    "TagName" text,
    "Count" integer,
    "ExcerptPostId" integer,
    "WikiPostId" integer,
    FOREIGN KEY ("ExcerptPostId") REFERENCES "posts" ("Id")
);

CREATE TABLE "users" (
    "Id" integer PRIMARY KEY,
    "Reputation" integer,
    "CreationDate" datetime,
    "DisplayName" text,
    "LastAccessDate" datetime,
    "WebsiteUrl" text,
    "Location" text,
    "AboutMe" text,
    "Views" integer,
    "UpVotes" integer,
    "DownVotes" integer,
    "AccountId" integer,
    "Age" integer,
    "ProfileImageUrl" text
);

CREATE TABLE "votes" (
    "Id" integer PRIMARY KEY,
    "PostId" integer,
    "VoteTypeId" integer,
    "CreationDate" date,
    "UserId" integer,
    "BountyAmount" integer,
    FOREIGN KEY ("UserId") REFERENCES "users" ("Id"),
    FOREIGN KEY ("PostId") REFERENCES "posts" ("Id")
);

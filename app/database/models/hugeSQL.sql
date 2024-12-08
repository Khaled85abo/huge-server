CREATE TABLE "job"(
    "id" BIGINT NOT NULL,
    "user_id" BIGINT NOT NULL,
    "source_storage" VARCHAR(255) NOT NULL,
    "dest_storage" VARCHAR(255) NOT NULL,
    "status" VARCHAR(255) CHECK
        ("status" IN('')) NOT NULL,
        "description" TEXT NOT NULL,
        "created_at" DATE NOT NULL,
        "updated_at" DATE NOT NULL
);
ALTER TABLE
    "job" ADD PRIMARY KEY("id");
CREATE TABLE "user"(
    "id" BIGINT NOT NULL,
    "org" VARCHAR(255) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "user" ADD PRIMARY KEY("id");
CREATE TABLE "sessions"(
    "session_token" VARCHAR(255) NOT NULL,
    "user_id" BIGINT NOT NULL,
    "last_accessed_at" DATE NOT NULL,
    "created_at" DATE NOT NULL,
    "expires_at" DATE NOT NULL,
    "ip_address" VARCHAR(255) NOT NULL,
    "is_active" BOOLEAN NOT NULL,
    "user_agent" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "sessions" ADD PRIMARY KEY("session_token");
ALTER TABLE
    "sessions" ADD CONSTRAINT "sessions_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "user"("id");
ALTER TABLE
    "job" ADD CONSTRAINT "job_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "user"("id");
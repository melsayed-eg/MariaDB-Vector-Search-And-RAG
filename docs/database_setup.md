
# MariaDB Database Setup

## Overview

This project uses MariaDB to store Wikipedia articles, text chunks, vector embeddings, categories, and links between articles.

MariaDB supports native vector similarity search alongside traditional relational SQL queries.

## Requirements

- Python 3.11 or newer
- MariaDB 11.8 or newer with native vector support
- Git
- Python virtual environment

Developed and tested using MariaDB 11.8.6.

The project uses 384-dimensional embeddings.

## 1. Install MariaDB

Install a compatible MariaDB server and ensure it is running.

Check the MariaDB server version:

```sql
SELECT VERSION();
```

## 2. Create the database

From the project root, run:

```bash
sudo mariadb < sql/setup.sql
```

This creates the `wikipedia_rag` database.

## 3. Create a database user

Connect to MariaDB as an administrator:

```bash
sudo mariadb
```

Run:

```sql
CREATE USER IF NOT EXISTS 'rag_app'@'localhost'
IDENTIFIED BY 'choose_a_secure_password';

GRANT SELECT, INSERT, UPDATE, DELETE
ON wikipedia_rag.*
TO 'rag_app'@'localhost';
```

Replace the example password with your own secure password.

The application account has data-access permissions. Schema creation requires an administrator account.

## 4. Create the database tables

From the project root, run:

```bash
sudo mariadb wikipedia_rag < sql/schema.sql
```

The schema creates five tables:

1. `articles` - Stores Wikipedia article content and metadata.
2. `chunks` - Stores article chunks and vector embeddings.
3. `categories` - Stores unique Wikipedia categories.
4. `article_categories` - Connects articles to categories.
5. `article_links` - Stores links between Wikipedia articles.

The `chunks` table contains a native vector index using cosine distance.

## 5. Configure environment variables

Copy the example configuration:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=wikipedia_rag
DB_USER=rag_app
DB_PASSWORD=your_actual_password
```

Replace the password with your own MariaDB password.

Never commit `.env` to GitHub.

## 6. Install Python dependencies

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

The database layer requires:

- PyMySQL
- python-dotenv

The development dependencies include pytest.

## 7. Verify the database connection

From the project root, run:

```bash
python -c "from src.database.connection import get_connection; c = get_connection(); print('Database connection successful'); c.close()"
```

Expected output:

```text
Database connection successful
```

## 8. Run automated tests

Run:

```bash
python -m pytest tests/ -v
```

The integration tests connect to a real MariaDB database.

Temporary test data is rolled back after testing.

Run these tests against a local development database, not a production database.

## 9. Verify the vector index

Connect to the database:

```bash
mariadb -u rag_app -p wikipedia_rag
```

Run:

```sql
SHOW INDEX FROM chunks;
```

The `embedding` vector index should be present.

## Important Notes

- Embeddings must contain exactly 384 finite numerical values.
- Article IDs correspond to Wikipedia article identifiers.
- Referenced articles must exist before links can be inserted.
- The database supports semantic vector search with relational SQL filters.
- The database schema enforces foreign key constraints.
- Deleting an article automatically deletes its associated chunks and relationships.
- Performance benchmarks should use real Wikipedia articles and embeddings.

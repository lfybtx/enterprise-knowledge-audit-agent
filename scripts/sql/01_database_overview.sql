-- Database overview for Enterprise Knowledge Audit Agent.
-- Run in Navicat, DBeaver, pgAdmin, or psql.

select current_database() as database_name, current_user as current_user, version() as postgres_version;

select extname as extension_name, extversion
from pg_extension
where extname in ('vector', 'plpgsql')
order by extname;

select version_num as alembic_version
from alembic_version;

select 'users' as table_name, count(*) as row_count from users
union all select 'knowledge_bases', count(*) from knowledge_bases
union all select 'knowledge_base_members', count(*) from knowledge_base_members
union all select 'documents', count(*) from documents
union all select 'document_permissions', count(*) from document_permissions
union all select 'document_chunks', count(*) from document_chunks
union all select 'workflow_runs', count(*) from workflow_runs
union all select 'workflow_trace_steps', count(*) from workflow_trace_steps
order by table_name;

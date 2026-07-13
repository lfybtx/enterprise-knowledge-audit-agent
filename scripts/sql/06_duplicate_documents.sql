-- Find possible duplicate document uploads by title, file type, and identical content.

select
    knowledge_base_id,
    title,
    file_type,
    md5(content) as content_hash,
    count(*) as duplicate_count,
    min(created_at) as first_seen_at,
    max(created_at) as last_seen_at
from documents
group by knowledge_base_id, title, file_type, md5(content)
having count(*) > 1
order by duplicate_count desc, last_seen_at desc;


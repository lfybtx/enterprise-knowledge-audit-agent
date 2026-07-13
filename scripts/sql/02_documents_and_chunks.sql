-- Document, chunk, and embedding status.

select
    d.id,
    kb.name as knowledge_base,
    d.title,
    d.file_type,
    d.status,
    count(c.id) as chunk_count,
    count(c.embedding) as embedded_chunk_count,
    d.created_at
from documents d
join knowledge_bases kb on kb.id = d.knowledge_base_id
left join document_chunks c on c.document_id = d.id
group by d.id, kb.name
order by d.created_at desc;

select
    d.title,
    c.chunk_index,
    c.location,
    left(c.text, 180) as preview,
    c.embedding is not null as has_embedding
from document_chunks c
join documents d on d.id = c.document_id
order by d.created_at desc, c.chunk_index
limit 50;


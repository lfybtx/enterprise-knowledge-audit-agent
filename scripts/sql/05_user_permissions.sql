-- Users, knowledge bases, and roles.

select
    u.external_id,
    u.display_name,
    kb.name as knowledge_base,
    kb.owner_id,
    m.role,
    m.created_at
from knowledge_base_members m
join users u on u.id = m.user_id
join knowledge_bases kb on kb.id = m.knowledge_base_id
order by kb.name, m.role, u.external_id;

select
    kb.name as knowledge_base,
    count(d.id) as document_count,
    count(distinct m.user_id) as member_count
from knowledge_bases kb
left join documents d on d.knowledge_base_id = kb.id
left join knowledge_base_members m on m.knowledge_base_id = kb.id
group by kb.id
order by kb.name;


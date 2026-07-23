import html


class SectionsNotApproved(Exception):
    pass


def _approved_sections(proposal):
    sections = list(proposal.sections.all())
    if not sections or any(section.state != 'approved' for section in sections):
        raise SectionsNotApproved
    return sections


def build_approved_markdown(proposal) -> str:
    sections = _approved_sections(proposal)
    meta = (proposal.content or {}).get('meta', {})
    title = html.escape(str(meta.get('title') or 'Proposal'), quote=False)
    lines = [f'# {title}']
    for section in sections:
        section_title = html.escape(str(section.title or section.key), quote=False)
        section_content = html.escape(str(section.approved_content or ''), quote=False)
        lines.extend(['', f'## {section_title}', section_content])
    return '\n'.join(lines)


def get_export_markdown(proposal) -> str:
    if proposal.final_markdown:
        _approved_sections(proposal)
        return proposal.final_markdown
    return build_approved_markdown(proposal)

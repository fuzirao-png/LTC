const procurementTerms = ['procurement', 'purchasing', 'strategic sourcing', '采购', '采买'];
const commercialTerms = ['commercial', 'business development', 'business manager', '商务', '商业'];
const managementTerms = ['manager', 'head', 'director', 'vice president', 'president', 'chief', 'lead', '经理', '主管', '总监', '负责人', '主任', '总裁', '首席'];
const text = (value) => String(value || '').replaceAll('\0', '').trim();
const first = (contact, keys) => keys.map((key) => text(contact?.[key])).find(Boolean) || '';

export const contactTitle = (contact) => first(contact, ['title', 'job_title', 'jobTitle', 'position', 'headline', 'role']);
export const contactEmail = (contact) => first(contact, ['email', 'email_address', 'emailAddress']);
export const contactPhone = (contact) => first(contact, ['phone', 'phone_number', 'phoneNumber']);
export const contactDisplayName = (contact) => first(contact, ['full_name', 'fullName', 'display_name', 'displayName', 'name'])
  || [first(contact, ['first_name', 'firstName']), first(contact, ['last_name', 'lastName'])].filter(Boolean).join(' ')
  || contactEmail(contact) || contactPhone(contact) || contactTitle(contact);
export const hasContactData = (contact) => Boolean(contactDisplayName(contact) || contactTitle(contact) || contactEmail(contact) || contactPhone(contact));

const seniorityRank = (title) => {
  const levels = [
    ['chairman', '董事长'],
    ['chief executive officer', 'ceo', 'president', 'founder', 'managing director', '首席执行官', '总裁', '总经理', '创始人'],
    ['chief ', 'cfo', 'cto', 'coo', 'cmo', '首席'],
    ['vice president', 'vp', '副总裁'],
    ['director', 'head', '总监', '负责人', '部长'],
    ['manager', '经理', '主管'],
    ['lead', 'principal', 'senior', '资深', '高级'],
  ];
  const rank = levels.findIndex((terms) => terms.some((term) => title.includes(term)));
  return rank < 0 ? levels.length : rank;
};

export const sortContacts = (contacts) => (Array.isArray(contacts) ? contacts : [])
  .filter((contact) => contact && typeof contact === 'object' && hasContactData(contact))
  .map((contact, index) => {
    const title = contactTitle(contact).toLowerCase();
    const managed = managementTerms.some((term) => title.includes(term));
    const category = managed && procurementTerms.some((term) => title.includes(term)) ? 0
      : managed && commercialTerms.some((term) => title.includes(term)) ? 1 : 2;
    return { contact, index, category, seniority: seniorityRank(title) };
  })
  .sort((a, b) => a.category - b.category || a.seniority - b.seniority || a.index - b.index)
  .map(({ contact }) => contact);

export const formatContactSummary = (contacts, limit = 2) => sortContacts(contacts)
  .map((contact) => [contactDisplayName(contact), contactTitle(contact)].filter(Boolean).join(' · '))
  .filter(Boolean).slice(0, limit).join('、');

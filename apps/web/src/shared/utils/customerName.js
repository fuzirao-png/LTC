export function websiteDomainPrefix(website) {
  const raw = String(website || '').trim();
  if (!raw) return '';
  try {
    const host = new URL(raw.includes('://') ? raw : `https://${raw}`).hostname.replace(/^www\./, '');
    return host.split('.')[0]?.toLowerCase() || '';
  } catch {
    return '';
  }
}

export function sanitizeCustomerName(candidates, website) {
  const normalizedDomainPrefix = websiteDomainPrefix(website).replace(/[^a-z0-9]/g, '');
  const isSafeName = (name) => {
    const normalized = name.toLowerCase().replace(/[^a-z0-9]/g, '');
    const isUppercaseBrand = /^[A-Z0-9]+$/.test(name) && /[A-Z]/.test(name);
    const isStandaloneDomainPrefix = normalizedDomainPrefix
      && normalized === normalizedDomainPrefix
      && !/\s/.test(name);
    return Boolean(name)
      && !name.includes('@')
      && !/^https?:\/\//i.test(name)
      && !/^[^\s@]+\.(com|net|org|io|co|cn|jp|kr)$/i.test(name)
      && (!isStandaloneDomainPrefix || isUppercaseBrand);
  };

  return candidates
    .map((candidate) => String(candidate || '').trim())
    .find(isSafeName) || '客户名称待确认';
}

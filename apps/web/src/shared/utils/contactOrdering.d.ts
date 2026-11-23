export type ContactLike = Record<string, unknown>;
export declare const contactDisplayName: (contact: ContactLike) => string;
export declare const contactTitle: (contact: ContactLike) => string;
export declare const contactEmail: (contact: ContactLike) => string;
export declare const contactPhone: (contact: ContactLike) => string;
export declare const hasContactData: (contact: ContactLike) => boolean;
export declare const sortContacts: <T extends ContactLike>(contacts: T[]) => T[];
export declare const formatContactSummary: (contacts: ContactLike[], limit?: number) => string;

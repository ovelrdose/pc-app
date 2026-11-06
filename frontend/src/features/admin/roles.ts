import type { UserRole } from '../../api/types';

/** Роли с доступом к админке целиком. */
export const ADMIN_ROLES: readonly UserRole[] = [
  'catalog_admin',
  'knowledge_engineer',
  'superadmin',
];

/** Роли, которым доступен раздел «Каталог». */
export const CATALOG_ROLES: readonly UserRole[] = ['catalog_admin', 'superadmin'];

/** Роли, которым доступен раздел «База знаний». */
export const KB_ROLES: readonly UserRole[] = ['knowledge_engineer', 'superadmin'];

/** Роли, которым доступен раздел «Пользователи». */
export const USERS_ROLES: readonly UserRole[] = ['superadmin'];

export interface AdminSection {
  path: string;
  title: string;
  /** Кто этим разделом пользуется (подпись на обзорной странице). */
  audience: string;
  description: string;
  roles: readonly UserRole[];
}

/** Разделы админки и требуемые роли (ADR 0010, п. 9). */
export const ADMIN_SECTIONS: readonly AdminSection[] = [
  {
    path: '/admin/catalog',
    title: 'Каталог',
    audience: 'Администратор каталога',
    description:
      'Комплектующие: создание и правка по фрейму категории, импорт CSV с пробным прогоном, экспорт, позиции, требующие внимания.',
    roles: CATALOG_ROLES,
  },
  {
    path: '/admin/kb',
    title: 'База знаний',
    audience: 'Инженер знаний',
    description:
      'Правила и справочники: редактор, проверка, публикация снимков, откат, экспорт знаний.',
    roles: KB_ROLES,
  },
  {
    path: '/admin/users',
    title: 'Пользователи',
    audience: 'Суперадминистратор',
    description:
      'Учётные записи: роли и блокировка. Недоступно самому себе и последнему активному суперадмину.',
    roles: USERS_ROLES,
  },
];

/** Разделы, доступные роли. */
export function sectionsForRole(role: UserRole): AdminSection[] {
  return ADMIN_SECTIONS.filter((section) => section.roles.includes(role));
}

/** Первый доступный раздел для роли (куда вести с `/admin`). */
export function homeSectionPath(role: UserRole): string {
  return sectionsForRole(role)[0]?.path ?? '/admin/catalog';
}

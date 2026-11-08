export const ADMIN_ROLES = ["academic_admin", "platform_admin"];
export const STAFF_ROLES = ["academic_admin", "support_staff", "platform_admin"];

export function can(user, roles) {
  return Boolean(user) && roles.includes(user.role);
}

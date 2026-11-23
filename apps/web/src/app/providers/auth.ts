import { useAuthStore as useBaseAuthStore } from '../../stores/auth'

/** Compatibility export for the API-aligned app views. */
export function useAuthStore() {
  const auth = useBaseAuthStore()
  return {
    ...auth,
    get actor() {
      const user = auth.currentUser
      if (!user) return null
      return {
        user_id: user.userId,
        username: user.username,
        display_name: user.name,
        account_type: user.accountType,
        sales_tier: user.salesTier || undefined,
        region_code: user.regionCode || undefined,
        capacity_limit: user.capacityLimit ?? undefined,
        active_assignment_count: user.activeAssignmentCount,
      }
    },
  }
}

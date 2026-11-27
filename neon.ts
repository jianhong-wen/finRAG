import { defineConfig } from "@neon/config/v1";

// Environments (ADR 0005): production is the default branch; these two persist.
const LONG_LIVED = ["development", "test"];

export default defineConfig({
  // Declare your Neon services here
  auth: false,
  // Branch policy: per-branch tuning
  branch: (branch) => {
    if (branch.isDefault) {
      // Default branch: no overrides, uses project defaults
      return {};
    }
    if (LONG_LIVED.includes(branch.name)) {
      // Long-lived environments (ADR 0005): never expire
      return {};
    }
    if (!branch.exists) {
      // New non-default branches: auto-expire
      // Run `neon checkout <name>` to create a new branch with these settings
      return { ttl: "7d" };
    }
    // Existing branch: no changes
    return {};
  },
});

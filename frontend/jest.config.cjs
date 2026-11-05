/** @type {import('jest').Config} */
module.exports = {
  watchman: false,
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.(t|j)sx?$": [
      "@swc/jest",
      {
        jsc: {
          parser: { syntax: "typescript", tsx: true },
          transform: { react: { runtime: "automatic" } },
        },
      },
    ],
  },
  moduleNameMapper: {
    "\\.(css)$": "<rootDir>/src/test/styles.cjs",
    "^@xyflow/react$": "<rootDir>/src/test/xyflow.tsx",
    "^react-router$": "<rootDir>/src/test/router.tsx",
    "^motion/react$": "<rootDir>/src/test/motion.tsx",
  },
  setupFilesAfterEnv: ["<rootDir>/src/test/setup.ts"],
  testMatch: ["<rootDir>/src/**/*.test.{ts,tsx}"],
  collectCoverageFrom: ["src/**/*.{ts,tsx}", "!src/main.tsx", "!src/test/**", "!src/**/*.test.*"],
  coverageThreshold: { global: { lines: 70, statements: 70 } },
};

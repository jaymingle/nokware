import { Account, Client } from "appwrite";

import { env } from "@/lib/env";

// Browser sign-in only. The portal's data comes from the Nokware API, which
// verifies a JWT from this account and decides the user's role itself.
const client = new Client().setEndpoint(env.appwriteEndpoint).setProject(env.appwriteProjectId);

export const account = new Account(client);

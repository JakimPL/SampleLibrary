import { describe, expect, it } from "vitest";

import { linkHost } from "../../src/shared/linkHost";

describe("linkHost", () => {
    it.each([
        ["https://www.modules.pl/?id=module&mod=9752", "modules.pl"],
        ["https://modarchive.org/index.php?request=view_by_moduleid&query=1", "modarchive.org"],
        ["http://www.example.org:8080/x", "example.org"],
    ])("names the site %s leads to as %s", (url, host) => {
        expect(linkHost(url)).toBe(host);
    });
});

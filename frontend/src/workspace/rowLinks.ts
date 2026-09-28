/**
 * Marks a control inside an entity row whose click the row's own click rule lets through: the
 * chevron that opens the entity, or a link that leaves the app for the page the entity came from.
 */
export const ROW_LINK_ATTRIBUTE = "data-row-link";

/** The attribute as props, spread onto the control. */
export const ROW_LINK_PROPS = { [ROW_LINK_ATTRIBUTE]: "" } as const;

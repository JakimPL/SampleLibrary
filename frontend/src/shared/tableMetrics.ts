// The height `table.data tbody tr` pins every listing row to in `styles.css`. A virtualizer places
// its rows from this number alone, so the two are kept equal deliberately: a row taller or shorter
// than the estimate drifts away from the scrollbar as a long listing is scrolled.
export const TABLE_ROW_HEIGHT_PX = 44;

// How many rows beyond the visible window a virtualized listing keeps rendered, so a fast scroll
// meets rows that are already there.
export const TABLE_OVERSCAN_ROWS = 12;

// The viewport height a virtualizer assumes before it has measured its own scroll container.
export const TABLE_INITIAL_VIEWPORT_HEIGHT_PX = 480;

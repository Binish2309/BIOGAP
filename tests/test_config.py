from src.config import BoundingBox


def test_rectangle_as_gbif_params_uses_lat_lon_ranges():
    bbox = BoundingBox(min_lat=18.75, max_lat=19.50, min_lon=72.75, max_lon=73.35)
    params = bbox.as_gbif_params()
    assert params["decimalLatitude"] == "18.75,19.5"
    assert "geometry" not in params


def test_polygon_as_gbif_params_uses_geometry():
    wkt = "POLYGON((72.75 18.75, 73.35 18.75, 73.35 19.5, 72.75 19.5, 72.75 18.75))"
    bbox = BoundingBox(polygon_wkt=wkt)
    params = bbox.as_gbif_params()
    assert params == {"geometry": wkt}


def test_contains_point_rectangle():
    bbox = BoundingBox(min_lat=18.75, max_lat=19.50, min_lon=72.75, max_lon=73.35)
    assert bbox.contains_point(19.0, 73.0) is True
    assert bbox.contains_point(20.0, 73.0) is False


def test_contains_point_polygon_excludes_corner_outside_triangle():
    # A right triangle covering only the lower-left half of the bbox rectangle.
    wkt = "POLYGON((72.75 18.75, 73.35 18.75, 72.75 19.50, 72.75 18.75))"
    bbox = BoundingBox(polygon_wkt=wkt)
    assert bbox.contains_point(18.80, 72.80) is True    # near the right-angle corner -- inside
    assert bbox.contains_point(19.45, 73.30) is False   # near the excluded corner -- outside the triangle

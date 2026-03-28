/**
 * Zillow integration stubs.
 *
 * These interfaces and placeholder implementations prepare for future
 * Zillow listing integration. The actual API calls will be implemented
 * when Zillow API access is obtained.
 */

export interface ZillowListing {
  zpid: string;
  address: string;
  city: string;
  state: string;
  zipCode: string;
  price: number;
  bedrooms: number;
  bathrooms: number;
  sqft: number;
  zestimate: number;
  pricePerSqft: number;
  coordinates: [number, number]; // [lng, lat]
  listingUrl: string;
  photoUrl?: string;
}

export interface ZillowSearchCriteria {
  minPrice?: number;
  maxPrice?: number;
  minBedrooms?: number;
  maxBedrooms?: number;
  minSqft?: number;
  maxSqft?: number;
  propertyType?: "house" | "condo" | "townhouse" | "multi-family" | "land";
}

export interface ZillowService {
  /** Search for listings within the given map bounds */
  searchListings(
    bounds: { west: number; south: number; east: number; north: number },
    criteria?: ZillowSearchCriteria
  ): Promise<ZillowListing[]>;

  /** Get detailed information about a specific property */
  getPropertyDetail(zpid: string): Promise<ZillowListing>;
}

/**
 * Placeholder implementation - returns empty results.
 * Replace with actual Zillow API integration when available.
 */
export const zillowService: ZillowService = {
  async searchListings() {
    console.warn("Zillow integration not yet implemented");
    return [];
  },

  async getPropertyDetail(zpid: string) {
    throw new Error(
      `Zillow integration not yet implemented (zpid: ${zpid})`
    );
  },
};

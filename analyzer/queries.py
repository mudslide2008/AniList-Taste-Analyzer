
LIST_QUERY = r"""
query ($userName: String!) {
  User(name: $userName) {
    id
    name
    siteUrl
    mediaListOptions { scoreFormat }
  }
  MediaListCollection(userName: $userName, type: ANIME) {
    lists {
      name
      isCustomList
      status
      entries {
        id status progress repeat
        scoreOriginal: score
        score3: score(format: POINT_3)
        score5: score(format: POINT_5)
        score10: score(format: POINT_10)
        score10Decimal: score(format: POINT_10_DECIMAL)
        score100: score(format: POINT_100)
        startedAt { year month day }
        completedAt { year month day }
        updatedAt
        media {
          id
          title { userPreferred romaji english native }
          format status episodes duration season seasonYear source genres
          meanScore averageScore popularity favourites siteUrl
          tags { name category rank isMediaSpoiler isGeneralSpoiler }
          studios(isMain: true) { nodes { id name siteUrl } }
        }
      }
    }
  }
}
"""

RECOMMENDATION_QUERY = r"""
query ($ids: [Int]) {
  Page(page: 1, perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      title { userPreferred romaji english }
      recommendations(perPage: 30, sort: RATING_DESC) {
        nodes {
          rating
          mediaRecommendation {
            id
            title { userPreferred romaji english }
            format seasonYear genres meanScore averageScore popularity siteUrl
            tags { name rank isMediaSpoiler isGeneralSpoiler }
          }
        }
      }
    }
  }
}
"""

STAFF_QUERY = r"""
query ($ids: [Int], $page: Int) {
  Page(page: $page, perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      staff(perPage: 25, sort: RELEVANCE) {
        edges {
          role
          node { id name { full } siteUrl }
        }
      }
    }
  }
}
"""
